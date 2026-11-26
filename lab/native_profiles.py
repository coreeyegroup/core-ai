#!/usr/bin/env python3
"""Separate isolated native profiles, with exact source/image approval and observed registration."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import manager
import native_host

PROFILES={
 "superpowers":{"repo":"obra/superpowers","commit":"22f0b463e7a5e579904dd6211a520321035526f7","entry":"index.js","directory":"/plugin"},
 "ponytail":{"repo":"dietrichgebert/ponytail","commit":"ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10","entry":".opencode/plugins/ponytail.mjs","directory":"/plugin/.opencode/plugins"},
 "i-have-adhd":{"repo":"ayghri/i-have-adhd","commit":"1ecea1993b7fce257ffbd686c070948b5e07eda6","entry":".opencode/plugins/i-have-adhd.mjs","directory":None},
}
# The discovery route follows the upstream loader-file convention. The directory
# route is separately reviewable. Profiles are never combined implicitly.
BOOTSTRAP='set -eu; mkdir -p "$XDG_CONFIG_HOME/opencode/plugins" /workspace; printf "%s\\n" "$PROFILE_CONFIG" > "$XDG_CONFIG_HOME/opencode/opencode.json"; if [ -n "$PROFILE_LOADER" ]; then printf "%s\\n" "$PROFILE_LOADER" > "$XDG_CONFIG_HOME/opencode/plugins/profile.js"; fi; unset OPENCODE_CONFIG; cd /workspace; exec node --input-type=module -e "$1"'
CHECKS=[["api","GET","/api/info"],["api","GET","/api/plugin"],["api","GET","/api/skill"]]

def plan(root,profile,route):
    cfg=PROFILES[profile]
    if route not in ("discovery","directory") or (route=="directory" and not cfg["directory"]):raise ValueError("Unsupported profile route")
    source=manager.source(root,cfg["repo"],cfg["commit"])
    manager.verify(source,cfg["commit"])
    if any(c in str(source) for c in ",\n\r"):raise ValueError("Unsafe source path")
    entry=source/cfg["entry"]
    if not entry.is_file() or not entry.resolve().is_relative_to(source.resolve()):raise ValueError("Missing or invalid pinned entry point")
    skills=sorted(p.name for p in (source/"skills").iterdir() if p.is_dir() and (p/"SKILL.md").is_file())
    if not skills:raise ValueError("Expected native skills not present")
    image,version=native_host.inspect_image(native_host.IMAGE_TAG)
    config={"plugins":[cfg["directory"]]} if route=="directory" else {}
    loader="export { default } from "+json.dumps("/plugin/"+cfg["entry"])+";" if route=="discovery" else ""
    return {"schema":2,"profile":profile,"route":route,"repo":cfg["repo"],"commit":cfg["commit"],"source":str(source),"image":image,
            "version":version,"expected_skills":skills,"config":config,"loader":loader,"bootstrap":BOOTSTRAP,"probe":Path(__file__).with_name("native_probe.mjs").read_text()+"\nawait main();","checks":CHECKS,"timeout":90}

def command(p,name):
    return ["docker","run","--rm","--name",name,"--pull=never","--network=none","--read-only","--user","1000:1000",
        "--cap-drop=ALL","--security-opt=no-new-privileges:true","--pids-limit=128","--memory=2g","--memory-swap=2g","--cpus=2",
        "--tmpfs","/tmp:rw,nosuid,nodev,size=256m,mode=1777",
        "--tmpfs","/home/node:rw,nosuid,nodev,size=256m,uid=1000,gid=1000,mode=0700",
        "--tmpfs","/workspace:rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700",
        "--workdir","/workspace","--mount","type=bind,src="+p["source"]+",dst=/plugin,readonly",
        "--env","PROFILE_CONFIG="+json.dumps(p["config"]),"--env","PROFILE_LOADER="+p["loader"],
        "--env","PROFILE_NAME="+p["profile"],"--env","PROFILE_SKILLS="+json.dumps(p["expected_skills"]),
        "--entrypoint","/bin/sh",p["image"],"-c",p["bootstrap"],"probe",p["probe"]]

def identifiers(raw):
    data=json.loads(raw)["data"]
    if not isinstance(data,list):raise ValueError("Expected list")
    return [v["id"] for v in data if isinstance(v,dict) and isinstance(v.get("id"),str) and re.fullmatch(r"[A-Za-z0-9_.:/@-]{1,160}",v["id"])][:300]

def registered(plugins,skills,profile,expected):
    return bool(expected) and profile in plugins and set(expected)<=set(skills)

def verify(root,p,approval):
    if native_host.digest(p)!=approval:raise ValueError("Approval does not match exact plan")
    if p!=plan(root,p["profile"],p["route"]):raise ValueError("Pinned profile changed")
    name="core-ai-native-profile-"+uuid.uuid4().hex
    results=[{"arguments":args,"state":"failed"} for args in p["checks"]]
    plugins=[];skills=[];version_ok=False
    try:
        proc=subprocess.run(command(p,name),timeout=p["timeout"],capture_output=True,text=True,check=False)
        for row in results:row["exit_code"]=proc.returncode
        if proc.returncode==0:
            data=json.loads(proc.stdout)
            version=data.get("version")
            version_ok=version==p["version"]
            results[0].update(state="version-matched" if version_ok else "version-mismatch",observed_version=version,attempts=data.get("attempts"),api_status=data.get("api_status",{}))
            plugins=identifiers(json.dumps({"data":[{"id":x} for x in data["plugins"]]}))
            skills=identifiers(json.dumps({"data":[{"id":x} for x in data["skills"]]}))
            results[1].update(state="observed",ids=plugins,failed=data.get("failed",[]))
            results[2].update(state="observed",ids=skills)
            results[0]["diagnostics"]=data.get("diagnostics",[])
    except subprocess.TimeoutExpired:
        results[0]["state"]="timeout"
        subprocess.run(["docker","kill",name],timeout=15,check=False,capture_output=True)
    except (ValueError,KeyError,TypeError,OSError):results[0]["state"]="invalid-api-result"
    ok=version_ok and registered(plugins,skills,p["profile"],p["expected_skills"])
    record={"plan":p,"approval":approval,"results":results,"registration":"observed" if ok else "not-observed","model_execution":"not-qualified"}
    path=manager.safe_path(root,"reports","native-profiles",uuid.uuid4().hex+".json")
    manager.write_new(path,record)
    print(json.dumps({"profile":p["profile"],"route":p["route"],"registration":record["registration"],"results":results,"report_id":path.stem},indent=2))
    return int(not ok)

def evidence(root):
    out=[]
    for name in PROFILES:
        row={"profile":name,"registration":"not-probed","model_execution":"not-qualified"}
        try:
            folder=manager.safe_path(root,"reports","native-profiles")
            if folder.is_dir():
                for path in sorted((p for p in folder.glob("*.json") if p.is_file() and not p.is_symlink()),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
                    if path.stat().st_size>256*1024:continue
                    r=json.loads(path.read_text());p=r.get("plan",{})
                    if p.get("profile")!=name or native_host.digest(p)!=r.get("approval"):continue
                    if p!=plan(root,name,p["route"]):continue
                    checks=r["results"];version_ok=any(c["arguments"]==["api","GET","/api/info"] and c["state"]=="version-matched" for c in checks)
                    ids=lambda endpoint:next((c.get("ids",[]) for c in checks if c["arguments"][-1]==endpoint),[])
                    ok=version_ok and registered(ids("/api/plugin"),ids("/api/skill"),name,p["expected_skills"])
                    row.update(registration="observed" if ok else "not-observed",route=p["route"],report_id=path.stem,checks=checks)
                    break
        except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
            row["registration"]="evidence-unavailable"
        out.append(row)
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    for action in ("review","verify"):
        p=sub.add_parser(action);p.add_argument("profile",choices=PROFILES);p.add_argument("--route",choices=("discovery","directory"),default="discovery")
        if action=="verify":p.add_argument("--approve",required=True)
    sub.add_parser("status")
    a=parser.parse_args()
    if a.action=="status":print(json.dumps(evidence(a.root),indent=2));return 0
    p=plan(a.root,a.profile,a.route)
    if a.action=="review":print(json.dumps(p,indent=2));print("Native profile approval digest:",native_host.digest(p));return 0
    return verify(a.root,p,a.approve)
if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:print("STOP:",type(exc).__name__,file=sys.stderr);sys.exit(1)
