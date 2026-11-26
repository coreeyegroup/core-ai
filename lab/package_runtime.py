#!/usr/bin/env python3
"""Review, build and verify pinned upstream package images; never install on the host."""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import manager
import native_host

NODE_BASE="core-ai-lab-opencode:0.1.0"
UV_BASE="ghcr.io/astral-sh/uv:python3.13-trixie-slim"
UA_ENTRY="/opt/upstream/understand-anything-plugin/packages/mcp/bin/understand-anything-mcp.mjs"
RECIPES={
 "understand-anything":{
  "repo":"egonex-ai/understand-anything","commit":"b232f356446295e4eaa05b9b285e08ce5cd5e8a0","base":NODE_BASE,
  "required":["package.json","pnpm-lock.yaml","pnpm-workspace.yaml","understand-anything-plugin/packages/mcp/package.json"],
  "build":"""USER root
RUN --network=default npm install --prefix /opt/pnpm --ignore-scripts --no-audit --no-fund pnpm@10.6.2
ENV PATH=/opt/pnpm/node_modules/.bin:$PATH HOME=/tmp/package-home
RUN --network=none mkdir -p /tmp/package-home /opt/upstream && chown -R 1000:1000 /tmp/package-home /opt/upstream
ADD --chown=1000:1000 source.tar /opt/upstream/
USER 1000:1000
WORKDIR /opt/upstream
RUN --network=default pnpm fetch --frozen-lockfile --ignore-scripts
RUN --network=none pnpm install --offline --frozen-lockfile
RUN --network=none pnpm --filter @understand-anything/core build && pnpm --filter @understand-anything/skill build && pnpm --filter @understand-anything/dashboard build && pnpm --filter understand-anything-viewer build
RUN --network=none pnpm --filter @understand-anything/core test
""",
  "server":["node",UA_ENTRY],"tools":["understand_status","understand_search","understand_explain"],
  "scope":"Core, skill, dashboard, viewer build and core tests; MCP tool discovery. LLM ingestion and project-specific graph use remain unqualified.",
 },
 "trading-skills":{
  "repo":"staskh/trading_skills","commit":"b025c283f16d6c49344d00e384b4b0cc347546da","base":UV_BASE,
  "required":["pyproject.toml","uv.lock","mcp_server/server.py"],
  "build":"""USER root
ENV HOME=/tmp/package-home UV_CACHE_DIR=/tmp/package-home/uv-cache UV_PYTHON_DOWNLOADS=never UV_NO_PROGRESS=1
RUN --network=none mkdir -p /tmp/package-home /opt/upstream && chown -R 1000:1000 /tmp/package-home /opt/upstream
ADD --chown=1000:1000 source.tar /opt/upstream/
USER 1000:1000
WORKDIR /opt/upstream
RUN --network=default uv sync --locked --no-dev
RUN --network=none .venv/bin/python -c "from trading_skills.black_scholes import black_scholes_price; assert abs(black_scholes_price(100,100,1,.05,.2,'call')-10.450583572185565)<1e-8"
""",
  "server":["/opt/upstream/.venv/bin/python","-m","mcp_server.server"],"tools":["get_version","stock_quote","option_greeks"],
  "scope":"Full locked Python package installation, offline pricing fixture and MCP discovery; no broker, account, market-data or live order access.",
 }
}
def inspect(tag):
    r=json.loads(subprocess.check_output(["docker","image","inspect",tag],text=True,timeout=15,stderr=subprocess.DEVNULL))
    if len(r)!=1 or not re.fullmatch(r"sha256:[0-9a-f]{64}",r[0]["Id"]):raise ValueError("Expected one local image")
    return r[0]

def plan(root,name):
    r=RECIPES[name]
    src=manager.source(root,r["repo"],r["commit"])
    manager.verify(src,r["commit"])
    for entry in r["required"]:
        p=src/entry
        if not p.is_file() or not p.resolve().is_relative_to(src.resolve()):raise ValueError("Required pinned package file missing")
    base=inspect(r["base"])
    dockerfile="FROM "+r["base"]+"\n"+r["build"]+"\nENTRYPOINT []\n"
    if any(not line.startswith(("RUN --network=default ","RUN --network=none ")) for line in dockerfile.splitlines() if line.startswith("RUN ")):raise ValueError("Every build command must declare its network policy")
    return {"schema":2,"build_network":"default","id":name,"repo":r["repo"],"commit":r["commit"],"source":str(src),"base":r["base"],"base_id":base["Id"],
        "dockerfile":dockerfile,"server":r["server"],"tools":r["tools"],"scope":r["scope"],
        "network":"dependency installation only; upstream build backend may run during Python dependency installation; offline runtime",
        "build_timeout":1800,"probe_timeout":90}

def image_tag(p):
    return "core-ai-lab-package-"+p["id"]+":"+native_host.digest(p)[:20]

def container_command(p,image,name):
    return ["docker","run","--rm","-i","--name",name,"--pull=never","--network=none","--read-only","--user","1000:1000",
        "--cap-drop=ALL","--security-opt=no-new-privileges:true","--pids-limit=128","--memory=2g","--memory-swap=2g","--cpus=2",
        "--tmpfs","/tmp:rw,nosuid,nodev,size=256m,mode=1777","--tmpfs","/workspace:rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700",
        "--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1","--workdir","/workspace","--entrypoint",p["server"][0],image,*p["server"][1:]]

class Stdio:
    """Bounded synchronous newline-framed MCP probe; no arbitrary subprocess input."""
    def __init__(self,proc,timeout):
        self.proc=proc;self.deadline=time.monotonic()+timeout;self.buffer=bytearray();self.seq=0
    def send(self,msg):
        self.proc.stdin.write((json.dumps(msg,separators=(",",":"))+"\n").encode());self.proc.stdin.flush()
    def receive(self,ident):
        with selectors.DefaultSelector() as sel:
            sel.register(self.proc.stdout,selectors.EVENT_READ)
            while time.monotonic()<self.deadline:
                if b"\n" in self.buffer:
                    raw,_,rest=self.buffer.partition(b"\n");self.buffer=bytearray(rest)
                    data=json.loads(raw)
                    if isinstance(data,dict) and data.get("id")==ident:
                        if data.get("error") or not isinstance(data.get("result"),dict):raise ValueError("MCP request rejected")
                        return data["result"]
                    continue
                if not sel.select(max(0,self.deadline-time.monotonic())):break
                chunk=os.read(self.proc.stdout.fileno(),65536)
                if not chunk:raise ValueError("MCP server closed the stream")
                self.buffer.extend(chunk)
                if len(self.buffer)>2*1024*1024:raise ValueError("MCP response too large")
        raise TimeoutError("MCP response deadline")
    def request(self,method,params):
        self.seq+=1
        self.send({"jsonrpc":"2.0","id":self.seq,"method":method,"params":params})
        return self.receive(self.seq)

def probe(p,image):
    name="core-ai-lab-package-probe-"+uuid.uuid4().hex
    with subprocess.Popen(container_command(p,image,name),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as proc:
        try:
            peer=Stdio(proc,p["probe_timeout"])
            hello=peer.request("initialize",{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"core-ai-lab","version":"1.0.0"}})
            if hello.get("protocolVersion") not in ("2024-11-05","2025-03-26","2025-06-18","2025-11-25","2026-07-28"):raise ValueError("Unsupported negotiated protocol")
            peer.send({"jsonrpc":"2.0","method":"notifications/initialized"})
            listing=peer.request("tools/list",{})
            ids=[x["name"] for x in listing["tools"] if isinstance(x,dict) and isinstance(x.get("name"),str)]
            if not set(p["tools"])<=set(ids):raise ValueError("Required tools not advertised")
            result={"protocol":hello["protocolVersion"],"tools":ids[:300],"offline_call":None}
            if p["id"]=="trading-skills":
                answer=peer.request("tools/call",{"name":"get_version","arguments":{}})
                if answer.get("isError") or "0.29.1" not in json.dumps(answer):raise ValueError("Installed package version mismatch")
                result["offline_call"]="get_version matched 0.29.1"
            return result
        finally:
            if proc.stdin:proc.stdin.close()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                subprocess.run(["docker","kill",name],check=False,timeout=15,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                proc.kill();proc.wait(timeout=5)

def build_command(p,context,approved):
    # RUN --network=default inherits the CLI build network mode. Explicit
    # --network=none instructions still remain offline with this default.
    return ["docker","build","--pull=false","--network="+p["build_network"],"--label","io.coreeye.lab.package.plan="+approved,
        "--label","io.coreeye.lab.package.source="+p["commit"],"--tag",image_tag(p),str(context)]

def install(root,name,approved):
    p=plan(root,name)
    if native_host.digest(p)!=approved:raise ValueError("Exact reviewed digest required")
    # Keep existing images and source trees untouched. Require room before an isolated build.
    if shutil.disk_usage(root).free<12*1024**3:raise ValueError("At least 12 GiB free lab storage required before package build")
    tag=image_tag(p)
    try:built=inspect(tag)
    except subprocess.CalledProcessError:built=None
    if built is None:
        with tempfile.TemporaryDirectory(prefix="core-ai-package-") as tmp:
            context=Path(tmp)/"context";context.mkdir()
            (context/"source.tar").write_bytes(manager.git(Path(p["source"]),"archive","--format=tar",p["commit"]))
            (context/"Dockerfile").write_text(p["dockerfile"])
            cfg=Path(tmp)/"docker-config";cfg.mkdir()
            env={k:os.environ[k] for k in ("PATH","LANG","LC_ALL") if k in os.environ}
            env.update(HOME=tmp,DOCKER_CONFIG=str(cfg),DOCKER_BUILDKIT="1")
            # No credentials, build secrets, host filesystem mounts or Docker socket are forwarded to the build.
            subprocess.run(build_command(p,context,approved),
                timeout=p["build_timeout"],check=True,env=env)
        built=inspect(tag)
    labels=built["Config"].get("Labels") or {}
    if labels.get("io.coreeye.lab.package.plan")!=approved or labels.get("io.coreeye.lab.package.source")!=p["commit"]:
        raise ValueError("Existing image differs from approved package build")
    if plan(root,name)!=p:raise ValueError("Source or base changed during build")
    evidence=probe(p,built["Id"])
    record={"plan":p,"approval":approved,"image":built["Id"],"probe":evidence,"state":"built-offline-smoke-passed"}
    path=manager.safe_path(root,"reports","packages",name,uuid.uuid4().hex+".json")
    manager.write_new(path,record)
    print(json.dumps({"id":name,"image":built["Id"],"state":record["state"],"probe":evidence,"report_id":path.stem},indent=2))
    return 0

def evidence(root):
    result=[]
    for name,r in RECIPES.items():
        row={"id":name,"repo":r["repo"],"commit":r["commit"],"state":"build-not-qualified","scope":r["scope"]}
        try:
            folder=manager.safe_path(root,"reports","packages",name)
            if folder.is_dir():
                for f in sorted((x for x in folder.glob("*.json") if x.is_file() and not x.is_symlink()),key=lambda x:x.stat().st_mtime,reverse=True)[:10]:
                    if f.stat().st_size>256*1024:continue
                    receipt=json.loads(f.read_text());p=receipt["plan"]
                    if p!=plan(root,name) or native_host.digest(p)!=receipt["approval"]:continue
                    image=inspect(image_tag(p));labels=image["Config"].get("Labels") or {}
                    if image["Id"]!=receipt["image"] or labels.get("io.coreeye.lab.package.plan")!=receipt["approval"]:continue
                    if not set(p["tools"])<=set(receipt["probe"]["tools"]):continue
                    if name=="trading-skills" and receipt["probe"].get("offline_call")!="get_version matched 0.29.1":continue
                    row.update(state="built-offline-smoke-passed",image=image["Id"],report_id=f.stem,tools=receipt["probe"]["tools"])
                    break
        except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):pass
        result.append(row)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=p.add_subparsers(dest="action",required=True)
    for action in ("review","install"):
        q=sub.add_parser(action);q.add_argument("package",choices=RECIPES)
        if action=="install":q.add_argument("--approve",required=True)
    sub.add_parser("status")
    a=p.parse_args()
    if a.action=="status":print(json.dumps(evidence(a.root),indent=2));return 0
    if a.action=="review":
        plan_data=plan(a.root,a.package);print(json.dumps(plan_data,indent=2));print("Package approval digest:",native_host.digest(plan_data));return 0
    return install(a.root,a.package,a.approve)
if __name__=="__main__":
    try:sys.exit(main())
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:print("STOP:",type(exc).__name__,file=sys.stderr);sys.exit(1)
