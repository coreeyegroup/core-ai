#!/usr/bin/env python3
"""One reviewed batch for independent native profiles and upstream package images."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid
import manager
import native_host
import native_profiles
import package_runtime

def plan(root,native_only=False):
    profiles=[]
    for name,cfg in native_profiles.PROFILES.items():
        routes=[native_profiles.plan(root,name,"discovery")]
        if cfg["directory"]:routes.append(native_profiles.plan(root,name,"directory"))
        profiles.append({"profile":name,"routes":routes})
    packages=[] if native_only else [package_runtime.plan(root,name) for name in package_runtime.RECIPES]
    return {"schema":1,"native_only":native_only,"profiles":profiles,"packages":packages,
            "preserve":"Existing source checkouts, 38 program receipts, runtime images and personal agent settings are not replaced.",
            "approval":"Review all exact routes, build scripts, local base images and network access before approval."}

def apply(root,p,approved):
    if native_host.digest(p)!=approved:raise ValueError("Batch digest differs from reviewed plan")
    if p!=plan(root,p["native_only"]):raise ValueError("Reviewed source, runtime or plan changed")
    results=[]
    for item in p["profiles"]:
        success=False
        for route in item["routes"]:
            try:
                rc=native_profiles.verify(root,route,native_host.digest(route))
                results.append({"kind":"native-profile","id":item["profile"],"route":route["route"],"state":"registration-observed" if rc==0 else "registration-not-observed"})
                if rc==0:success=True;break
            except (ValueError,OSError,subprocess.SubprocessError) as exc:
                results.append({"kind":"native-profile","id":item["profile"],"route":route["route"],"state":"failed","error_type":type(exc).__name__})
        results.append({"kind":"native-summary","id":item["profile"],"state":"registration-observed" if success else "registration-not-observed"})
    for package in p["packages"]:
        try:
            if package!=package_runtime.plan(root,package["id"]):raise ValueError("Package plan changed")
            rc=package_runtime.install(root,package["id"],native_host.digest(package))
            results.append({"kind":"package","id":package["id"],"state":"built-offline-smoke-passed" if rc==0 else "failed"})
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            results.append({"kind":"package","id":package["id"],"state":"failed","error_type":type(exc).__name__})
    failures=[r for r in results if r["kind"] in ("native-summary","package") and r["state"] not in ("registration-observed","built-offline-smoke-passed")]
    record={"plan":p,"approval":approved,"results":results,"failed":len(failures)}
    report=manager.safe_path(root,"reports","platform-batches",uuid.uuid4().hex+".json")
    manager.write_new(report,record)
    print(json.dumps({"report_id":report.stem,"results":results,"failed":len(failures)},indent=2))
    return int(bool(failures))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    for action in ("review","apply"):
        q=sub.add_parser(action);q.add_argument("--native-only",action="store_true")
        if action=="apply":q.add_argument("--approve",required=True)
    sub.add_parser("status")
    a=parser.parse_args()
    if a.action=="status":
        print(json.dumps({"native_profiles":native_profiles.evidence(a.root),"packages":package_runtime.evidence(a.root)},indent=2));return 0
    p=plan(a.root,a.native_only)
    if a.action=="review":
        print(json.dumps(p,indent=2));print("Platform approval digest:",native_host.digest(p));return 0
    return apply(a.root,p,a.approve)
if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:print("STOP:",type(exc).__name__,file=sys.stderr);sys.exit(1)
