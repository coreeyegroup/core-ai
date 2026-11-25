"""Authenticated CORE-AI access to the independent lab's private Unix socket."""
import base64
import hashlib
import json
import os
import socket
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from . import access, auth, db, files

router=APIRouter(prefix="/api/v1/programs")
SOCKET="/run/core-ai-lab/gateway.sock"
MAX_FRAME=10*1024*1024

class RunInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    recipe:str=Field(min_length=1,max_length=80,pattern=r"^[a-z0-9-]+$")
    values:list[Any]=Field(default_factory=list,max_length=1000)
    extension:str|None=Field(default=None,max_length=8,pattern=r"^\.[a-z0-9]+$")
    file_data:str|None=Field(default=None,max_length=5592408)

class AgentProgram(BaseModel):
    model_config=ConfigDict(extra="forbid")
    recipe:str=Field(min_length=1,max_length=80,pattern=r"^[a-z0-9-]+$")
    values:list[Any]=Field(default_factory=list,max_length=1000)
    file_id:uuid.UUID|None=None

class Discover(BaseModel):
    model_config=ConfigDict(extra="forbid")

def request(payload,timeout=210):
    try:
        raw=json.dumps(payload,allow_nan=False,separators=(",",":")).encode()+b"\n"
        if len(raw)>MAX_FRAME: raise HTTPException(413,"Program request exceeds the size limit.")
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(os.environ.get("CORE_AI_LAB_SOCKET",SOCKET))
            conn.sendall(raw)
            with conn.makefile("rb") as stream:
                reply=stream.readline(MAX_FRAME+1)
        if not reply.endswith(b"\n") or len(reply)>MAX_FRAME:
            raise ValueError("Invalid response")
        data=json.loads(reply)
    except HTTPException: raise
    except (OSError,ValueError,TypeError,OverflowError):
        raise HTTPException(503,"Independent program gateway unavailable or returned an invalid response.") from None
    if not isinstance(data,dict) or data.get("ok") is not True:
        status={"busy":409,"rejected":422,"unavailable":503}.get(data.get("code") if isinstance(data,dict) else None,503)
        raise HTTPException(status,"Program execution rejected, busy or unavailable. Check inputs and lab reports.")
    return data["data"]

def get_catalog():
    return request({"action":"catalog"},timeout=45)

@router.get("")
def list_programs(user=Depends(auth.session)):
    return get_catalog()

def invoke(body):
    return request({"action":"run",**body.model_dump()})

@router.post("/run")
def manual_run(body:RunInput,user=Depends(auth.session)):
    access.writer(user)
    db.event("program.requested",user["id"],{"recipe":body.recipe})
    try:
        result=invoke(body)
    except HTTPException:
        db.event("program.failed",user["id"],{"recipe":body.recipe})
        raise
    db.event("program.completed",user["id"],{"recipe":body.recipe,"execution_id":result["id"],"commit":result["commit"]})
    return result

def agent_catalog():
    catalog=get_catalog()
    return {"programs":[{k:p[k] for k in ("id","fields","example","extensions","mode")}
                        for p in catalog["programs"] if p["state"]=="qualified-receipt"]}

def agent_run(body,user,run):
    extension=None
    data=None
    if body.file_id is not None:
        from pathlib import PurePath
        with db.connect() as conn:
            if run["project_id"] is not None:access.project(conn,user,run["project_id"])
            if run.get("chat_generation") and str(body.file_id) not in run["attached_file_ids"]:
                raise HTTPException(403,"Choose an attachment from the current message.")
            row=files.owned(conn,user,body.file_id)
            if row["project_id"]!=run["project_id"]:
                raise HTTPException(403,"Choose a file in the current project.")
            raw=bytes(row["raw"])
        if len(raw)>4*1024*1024: raise HTTPException(413,"Program input exceeds 4 MiB.")
        extension=PurePath(row["name"]).suffix.lower()
        data=base64.b64encode(raw).decode("ascii")
    result=invoke(RunInput(recipe=body.recipe,values=body.values,extension=extension,file_data=data))
    generated=result.pop("file",None)
    if generated:
        raw=base64.b64decode(generated["data"],validate=True)
        name=generated["name"]
        # Notebook is retained as JSON for the existing file library parser.
        if name=="result.ipynb": name="result.ipynb.json"
        if name not in ("result.docx","result.xlsx","result.ipynb.json") or len(raw)>files.MAX_BYTES:
            raise HTTPException(422,"Unexpected generated file.")
        with db.connect() as conn:
            if run["project_id"] is not None:access.project(conn,user,run["project_id"],True)
            table="chat_generations" if run.get("chat_generation") else "runs"
            state=conn.execute(f"SELECT status FROM {table} WHERE id=%s FOR UPDATE",(run["id"],)).fetchone()
            if not state or state["status"]!="RUNNING": raise InterruptedError("Run stopped before saving output.")
            conn.execute("SELECT pg_advisory_xact_lock(187875438)")
            quota=conn.execute("SELECT coalesce(sum(size_bytes),0) AS n FROM workspace_files WHERE owner_id=%s",(user["id"],)).fetchone()["n"]
            pending=conn.execute("SELECT count(*) AS n FROM workspace_files WHERE status IN ('QUEUED','PROCESSING')").fetchone()["n"]
            if quota+len(raw)>500*1024*1024 or pending>=20:
                raise HTTPException(409,"File library quota or queue limit reached.")
            ident=uuid.uuid4()
            conn.execute("INSERT INTO workspace_files(id,owner_id,project_id,name,media_type,size_bytes,sha256,raw,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'QUEUED')",
                         (ident,user["id"],run["project_id"],name,"application/octet-stream",len(raw),hashlib.sha256(raw).hexdigest(),raw))
            db.event("file.uploaded",user["id"],{"file_id":str(ident),"bytes":len(raw)},conn=conn)
        result["file_id"]=str(ident)
        result["file_name"]=name
    # Never put base64, huge results, or unbounded text into model context.
    raw=json.dumps(result.get("result"),ensure_ascii=False)
    if len(raw)>12000:
        result["result"]={"preview":raw[:10000],"truncated":True}
    return result
