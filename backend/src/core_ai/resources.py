"""Read-only server and model-provider observations; never equate remote model memory to free host RAM."""
import os
from pathlib import Path
import shutil
from datetime import datetime,timezone
from fastapi import APIRouter,Depends
from . import auth,access,models
import httpx
router=APIRouter(prefix="/api/v1/resources")

def local():
    result={"scope":"core-ai-server","observed_at":datetime.now(timezone.utc).isoformat(),"cpu_logical":os.cpu_count(),"memory":None,"disk":None,"load_1m":None}
    try:
        info={}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key,_,value=line.partition(":")
            if key in ("MemTotal","MemAvailable"):info[key]=int(value.split()[0])*1024
        if len(info)==2:result["memory"]={"total_bytes":info["MemTotal"],"available_bytes":info["MemAvailable"]}
    except (OSError,ValueError,IndexError):pass
    try:result["load_1m"]=os.getloadavg()[0]
    except OSError:pass
    try:
        usage=shutil.disk_usage("/var/lib/core-ai" if Path("/var/lib/core-ai").exists() else "/")
        result["disk"]={"total_bytes":usage.total,"free_bytes":usage.free}
    except OSError:pass
    return result

def provider():
    try:
        with httpx.Client(timeout=5,trust_env=False,follow_redirects=False) as c:
            r=c.get(models.config()["endpoint"]+"/api/ps");r.raise_for_status()
            items=r.json()["models"]
        return {"available":True,"scope":"ollama-provider-reported-loaded-models","models":[{k:v[k] for k in ("name","size","size_vram","context_length","expires_at") if k in v} for v in items[:32] if isinstance(v,dict)],
                "free_ram_bytes":None,"free_vram_bytes":None}
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        return {"available":False,"scope":"ollama-provider","models":[],"free_ram_bytes":None,"free_vram_bytes":None}

@router.get("")
def status(user=Depends(auth.session)):
    access.admin(user)
    return {"server":local(),"provider":provider()}
