#!/usr/bin/env python3
"""Review, install and report all currently reviewed independent recipes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

import manager
import programs
import document_programs as docs
import trading_programs as trading
import more_programs as more
import quant_programs as quant
import research_programs as research
import coverage_programs as coverage

PYTHON="python:3.12-slim"
DOCUMENTS="core-ai-lab-documents:0.1.0"
OFFICE="core-ai-lab-office:0.1.0"

def catalog():
    entries=[("ui-ux-pro-max",PYTHON,programs)]
    entries += [(n,OFFICE if n in docs.EDIT_RECIPES else DOCUMENTS,docs) for n in docs.RECIPES]
    entries += [(n,PYTHON,trading) for n in trading.RECIPES]
    entries += [(n,PYTHON,more) for n in more.RECIPES]
    entries += [(n,r["runtime"],quant) for n,r in quant.RECIPES.items()]
    entries += [(n,PYTHON,research) for n in research.RECIPES]
    entries += [(n,r["runtime"],coverage) for n,r in coverage.RECIPES.items()]
    if len({n for n,_,_ in entries})!=len(entries):
        raise ValueError("Duplicate recipe identifier")
    return entries

def image_id(tag):
    raw=subprocess.check_output(["docker","image","inspect","--format","{{.Id}}",tag],text=True,timeout=15).strip()
    if not manager.IMAGE.fullmatch(raw):
        raise ValueError("Unexpected image ID for "+tag)
    return raw

def plan_for(module,name,image):
    return module.plan(name,image,smoke=True) if module is programs else module.plan(name,image)

def receipt_for(module,root,name,image):
    return (module.receipt_path(root,name,image),module.receipt(name,image)) if module is programs else module.receipt(root,name,image)

def verified_receipt(module,root,name,image):
    path,data=receipt_for(module,root,name,image)
    if path.exists():
        if not path.is_file() or json.loads(path.read_text())!=data:
            raise ValueError("Receipt mismatch: "+name)
        return True
    return False

def reviewed_plan(root):
    pins=manager.load_manifest(manager.HERE/"repositories.json")
    images={tag:image_id(tag) for tag in sorted({tag for _,tag,_ in catalog()})}
    rows=[]
    for name,tag,module in catalog():
        p=plan_for(module,name,images[tag])
        if pins.get(p["repo"])!=p["commit"]:
            raise ValueError("Recipe pin differs from manifest: "+name)
        manager.verify(manager.source(root,p["repo"],p["commit"]),p["commit"])
        rows.append({"recipe":name,"runtime":tag,"plan":p,"digest":manager.digest(p)})
    # Include all qualification plans, not just the currently missing ones;
    # completing a subset does not invalidate an approved batch.
    return {"schema":1,"recipes":rows}

def digest(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def install(root,approved):
    plan=reviewed_plan(root)
    if digest(plan)!=approved:
        raise ValueError("Batch approval differs; review the current exact plans and images")
    modules={name:module for name,_,module in catalog()}
    results=[]
    for row in plan["recipes"]:
        name=row["recipe"]
        p=row["plan"]
        module=modules[name]
        result={"recipe":name,"repo":p["repo"],"commit":p["commit"],"image":p["image"],"state":"failed"}
        try:
            manager.verify(manager.source(root,p["repo"],p["commit"]),p["commit"])
            if verified_receipt(module,root,name,p["image"]):
                result["state"]="already-qualified"
            else:
                rc=module.install(root,name,p["image"],row["digest"])
                if rc==0 and verified_receipt(module,root,name,p["image"]):
                    result["state"]="qualified"
                else:
                    result["exit_code"]=rc
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            result["error_type"]=type(exc).__name__
            print("FAILED",name,str(exc),file=sys.stderr)
        results.append(result)
        print(name,result["state"],flush=True)
    path=manager.safe_path(root,"reports","batches",uuid.uuid4().hex+".json")
    manager.write_new(path,{"approval":approved,"results":results})
    print("Batch report:",path)
    return int(any(r["state"]=="failed" for r in results))

def status(root):
    pins=manager.load_manifest(manager.HERE/"repositories.json")
    rows={repo:{"repository":repo,"commit":commit,"source_present":False,"recipes":[],"coverage":"not-reviewed-for-installation"} for repo,commit in pins.items()}
    for repo,row in rows.items():
        try:
            manager.verify(manager.source(root,repo,row["commit"]),row["commit"])
            row["source_present"]=True
        except (ValueError,OSError,subprocess.SubprocessError):
            pass
    for name,tag,module in catalog():
        # A dummy digest is used only to identify the repository when the
        # runtime is absent; it is never executed or recorded as qualified.
        p=plan_for(module,name,"sha256:"+"0"*64)
        row=rows[p["repo"]]
        row["coverage"]="partial-reviewed-recipes"
        state="pending"
        try:
            image=image_id(tag)
            if row["source_present"] and verified_receipt(module,root,name,image):
                state="qualified-receipt"
        except (ValueError,OSError,subprocess.SubprocessError):
            state="review-required"
        row["recipes"].append({"recipe":name,"runtime":tag,"state":state})
    print(json.dumps({"repositories":list(rows.values())},indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("list")
    sub.add_parser("review")
    sub.add_parser("status")
    q=sub.add_parser("install")
    q.add_argument("--approve",required=True)
    a=parser.parse_args()
    if a.action=="list":
        for name,tag,module in catalog(): print(name,tag)
        return 0
    if a.action=="status":
        status(a.root)
        return 0
    if a.action=="review":
        p=reviewed_plan(a.root)
        print(json.dumps(p,indent=2))
        print("Batch approval digest:",digest(p))
        return 0
    return install(a.root,a.approve)

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print("STOP:",str(exc),file=sys.stderr)
        sys.exit(1)
