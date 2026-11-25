#!/usr/bin/env python3
"""Review and probe an isolated OpenCode V2 host with the pinned Superpowers plugin."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

import manager

REPO="obra/superpowers"
COMMIT="22f0b463e7a5e579904dd6211a520321035526f7"
IMAGE_TAG="core-ai-lab-opencode:0.1.0"

def inspect_image(tag):
    data=json.loads(subprocess.check_output(["docker","image","inspect",tag],text=True,timeout=15))
    if len(data)!=1: raise ValueError("Expected one local image")
    image=data[0]
    image_id=image["Id"]
    labels=image["Config"].get("Labels") or {}
    version=labels.get("io.coreeye.lab.opencode.version","")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",image_id):
        raise ValueError("Invalid local image ID")
    if not re.fullmatch(r"2\.\d+\.\d+",version) or tuple(map(int,version.split(".")))<(2,0,4):
        raise ValueError("Expected a reviewed OpenCode V2 image >=2.0.4")
    if labels.get("io.coreeye.lab.runtime")!="opencode":
        raise ValueError("Expected the lab native runtime image")
    return image_id,version

def plan(root,image_tag):
    source=manager.source(root,REPO,COMMIT)
    manager.verify(source,COMMIT)
    if any(c in str(source) for c in ",\n\r"):
        raise ValueError("Unsafe bind mount path")
    image,version=inspect_image(image_tag)
    return {"schema":1,"repo":REPO,"commit":COMMIT,"source":str(source),
            "image":image,"host_version":version,
            "checks":[["--version"],["plugin","list"]],
            "network":"none","timeout":90}

def digest(p):
    return hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def command(p,args,name):
    return ["docker","run","--rm","--name",name,"--pull=never","--network=none",
            "--read-only","--user","1000:1000","--cap-drop=ALL",
            "--security-opt=no-new-privileges:true","--pids-limit=128","--cpus=2",
            "--memory=2g","--memory-swap=2g",
            "--tmpfs","/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--tmpfs","/home/node:rw,nosuid,nodev,size=256m,uid=1000,gid=1000,mode=0700",
            "--tmpfs","/workspace:rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700",
            "--mount","type=bind,src="+p["source"]+",dst=/plugins/superpowers,readonly",
            p["image"],*args]

def verify(root,image_tag,approved):
    p=plan(root,image_tag)
    if digest(p)!=approved:
        raise ValueError("Approval differs from exact image and source plan")
    results=[]
    for args in p["checks"]:
        name="core-ai-lab-native-"+uuid.uuid4().hex
        result={"arguments":args,"state":"failed"}
        try:
            proc=subprocess.run(command(p,args,name),timeout=p["timeout"],
                                capture_output=True,text=True,check=False)
            print(proc.stdout,end="")
            if proc.stderr: print(proc.stderr,end="",file=sys.stderr)
            result["exit_code"]=proc.returncode
            if proc.returncode==0:
                if args==["--version"]:
                    result["state"]="version-matched" if p["host_version"] in proc.stdout else "version-mismatch"
                else:
                    # The CLI's text output is not a stable machine-readable
                    # registration contract. Require a human to inspect it.
                    result["state"]="registration-review-required" if re.search(r"\bsuperpowers\b",proc.stdout,re.I) else "plugin-not-listed"
        except subprocess.TimeoutExpired:
            result["state"]="timeout"
            subprocess.run(["docker","kill",name],timeout=15,check=False,capture_output=True)
        results.append(result)
    record=manager.safe_path(root,"reports","native",uuid.uuid4().hex+".json")
    manager.write_new(record,{"plan":p,"approval":approved,"results":results,
                              "qualification":"manual-plugin-status-review-required"})
    print("Native probe record:",record)
    return int([r["state"] for r in results]!=["version-matched","registration-review-required"])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    for action in ("review","verify"):
        q=sub.add_parser(action)
        q.add_argument("--image",default=IMAGE_TAG)
        if action=="verify": q.add_argument("--approve",required=True)
    a=parser.parse_args()
    if a.action=="review":
        p=plan(a.root,a.image)
        print(json.dumps(p,indent=2))
        print("Native approval digest:",digest(p))
        return 0
    return verify(a.root,a.image,a.approve)

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print("STOP:",str(exc),file=sys.stderr)
        sys.exit(1)
