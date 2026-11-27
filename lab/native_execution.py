#!/usr/bin/env python3
"""Reviewed, model-specific native execution. No host credentials, network or workspace mounts."""
import argparse
from http.server import BaseHTTPRequestHandler
import http.client
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid
import manager
import native_host
import native_profiles

PROFILES={"superpowers":("superpowers",),"ponytail":("ponytail",),"combined":("superpowers","ponytail")}
MODES=("lite","full","ultra")
MAX_BODY=4*1024*1024
MAX_RESPONSE=8*1024*1024
TIMEOUT=540
INFERENCE_TIMEOUT=300
MAX_CALLS=16

def timeout_settings():
    # Operator settings are part of the reviewed plan, never model/tool input.
    try:
        task=int(os.environ.get("CORE_AI_NATIVE_TASK_SECONDS",TIMEOUT))
        inference=int(os.environ.get("CORE_AI_NATIVE_INFERENCE_SECONDS",INFERENCE_TIMEOUT))
    except ValueError:
        raise ValueError("Invalid native timeout settings") from None
    if not 180<=task<=540 or not 30<=inference<=300 or inference+60>task:
        raise ValueError("Native timeouts outside approved bounds")
    return task,inference

def endpoint(value):
    u=urlsplit(value)
    if u.scheme!="http" or u.username or u.password or u.path not in ("","/") or u.query or u.fragment:
        raise ValueError("Expected private Ollama IPv4 HTTP endpoint")
    ip=ipaddress.IPv4Address(u.hostname)
    port=u.port if u.port is not None else 80
    if not 1<=port<=65535 or not any(ip in ipaddress.IPv4Network(x) for x in ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","127.0.0.0/8")):
        raise ValueError("Expected private Ollama IPv4 endpoint")
    return f"http://{ip}:{port}"

def validate_request(method,path,body,model):
    if method=="GET" and path=="/api/tags" and body is None:return
    if method!="POST" or path not in ("/api/show","/v1/chat/completions") or not isinstance(body,dict) or body.get("model")!=model:
        raise ValueError("Unapproved model or operation")
    if path=="/api/show" and set(body)!={"model"}:raise ValueError("Unexpected show input")
    if path=="/v1/chat/completions":
        if not isinstance(body.get("messages"),list) or len(body["messages"])>200:raise ValueError("Invalid messages")
        if body.get("n",1)!=1:raise ValueError("Only one completion per request")

def connection(url,timeout=30):
    u=urlsplit(url)
    return http.client.HTTPConnection(u.hostname,u.port,timeout=timeout)

def fetch_json(url,path,body=None):
    c=connection(url)
    try:
        c.request("GET" if body is None else "POST",path,None if body is None else json.dumps(body).encode(),{"Content-Type":"application/json"})
        response=c.getresponse()
        if response.status!=200:raise ValueError("Ollama inventory unavailable")
        raw=response.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE:raise ValueError("Ollama response too large")
        return json.loads(raw)
    finally:c.close()

def model_snapshot(url,model):
    if not isinstance(model,str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,120}",model) or model.endswith(":cloud"):
        raise ValueError("Select a local model")
    rows=fetch_json(url,"/api/tags")["models"]
    item=next((x for x in rows if x.get("model")==model),None)
    if not item or item.get("remote_model") or item.get("remote_host") or not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}",item.get("digest","")):
        raise ValueError("Selected local model not installed")
    show=fetch_json(url,"/api/show",{"model":model})
    if not {"completion","tools"}<=set(show.get("capabilities",[])):
        raise ValueError("Model must support generation and tools")
    return item,show

def plan(root,profile,url,model,mode):
    if profile not in PROFILES or mode not in MODES or (profile=="superpowers" and mode!="full"):
        raise ValueError("Unknown profile or mode")
    url=endpoint(url)
    entries=[native_profiles.plan(root,x,"directory") for x in PROFILES[profile]]
    image=entries[0]["image"]
    if any(x["image"]!=image for x in entries):raise ValueError("Runtime changed")
    item,_=model_snapshot(url,model)
    task_timeout,inference_timeout=timeout_settings()
    plugins=["/profiles/"+x["profile"]+("/.opencode/plugins" if x["profile"]=="ponytail" else "") for x in entries]
    return {"schema":1,"profile":profile,"mode":mode,"endpoint":url,"model":model,"model_digest":item["digest"],
        "image":image,"version":entries[0]["version"],"sources":[{k:x[k] for k in ("profile","source","repo","commit","expected_skills")} for x in entries],
        "config":{"plugins":plugins,"providers":{"ollama":{"settings":{"baseURL":"http://127.0.0.1:11434/v1"}}}},
        "runner":Path(__file__).with_name("native_execution.mjs").read_text(),"implementation":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timeout":task_timeout,"inference_timeout":inference_timeout,"max_model_calls":MAX_CALLS,"network":"none; only exact local Ollama model via filtered Unix socket"}

def command(p,name,socket_path):
    args=["docker","run","--rm","-i","--name",name,"--pull=never","--network=none","--read-only","--user","1000:1000",
          "--cap-drop=ALL","--security-opt=no-new-privileges:true","--pids-limit=128","--memory=2g","--memory-swap=2g","--cpus=2",
          "--tmpfs","/tmp:rw,nosuid,nodev,size=256m,mode=1777",
          "--tmpfs","/home/node:rw,nosuid,nodev,size=256m,uid=1000,gid=1000,mode=0700",
          "--tmpfs","/workspace:rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700",
          "--workdir","/workspace","--mount","type=bind,src="+str(socket_path)+",dst=/relay.sock,readonly"]
    for src in p["sources"]:
        args.extend(["--mount","type=bind,src="+src["source"]+",dst=/profiles/"+src["profile"]+",readonly"])
    return args+["--env","NATIVE_CONFIG="+json.dumps(p["config"]),"--env","NATIVE_MODEL="+p["model"],
        "--env","NATIVE_EXPECTED="+json.dumps({"version":p["version"],"sources":[{"profile":x["profile"],"expected_skills":x["expected_skills"]} for x in p["sources"]]}),
        "--env","PONYTAIL_DEFAULT_MODE="+p["mode"],"--env","OPENCODE_DISABLE_MODELS_FETCH=1",
        "--entrypoint","node",p["image"],"--input-type=module","-e",p["runner"]]

class Relay(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    request_queue_size=4
    def __init__(self,path,p,item,show):
        super().__init__(str(path),Handler)
        self.p=p;self.item=item;self.show=show
        self.calls=0;self.hook=False;self.lock=threading.Lock();self.slot=threading.BoundedSemaphore(2)
        self.failures=[]
    def note_failure(self,code):
        with self.lock:
            if len(self.failures)<32:self.failures.append(code)
    def diagnostics(self):
        with self.lock:return sorted(set(self.failures))
    def process_request(self,request,address):
        if not self.slot.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slot.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slot.release()

class Handler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.0"
    def log_message(self,*args):pass
    def setup(self):
        self.request.settimeout(20)
        super().setup()
    def do_GET(self):self.handle_request()
    def do_POST(self):self.handle_request()
    def send_json(self,data):
        raw=json.dumps(data).encode()
        self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def handle_request(self):
        c=None;started=False;stage="request"
        try:
            if self.headers.get("Transfer-Encoding"):raise ValueError("Unsupported request encoding")
            body=None
            if self.command=="POST":
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=MAX_BODY:raise ValueError("Body exceeds limit")
                body=json.loads(self.rfile.read(length))
            p=self.server.p
            validate_request(self.command,self.path,body,p["model"])
            if self.path=="/api/tags":self.send_json({"models":[self.server.item]});return
            if self.path=="/api/show":self.send_json(self.server.show);return
            with self.server.lock:
                if self.server.calls>=MAX_CALLS:raise ValueError("Model call budget exhausted")
                self.server.calls+=1
                marker="PONYTAIL MODE ACTIVE — level: "+p["mode"]
                self.server.hook |= any(isinstance(m,dict) and m.get("role")=="system" and marker in json.dumps(m.get("content"),ensure_ascii=False) for m in body["messages"])
            # Do not forward client headers, authentication, proxy settings or redirects.
            body["max_tokens"]=min(4096,max(1,int(body.get("max_tokens") or 4096)))
            stage="upstream"
            c=connection(p["endpoint"],p.get("inference_timeout",INFERENCE_TIMEOUT))
            c.request("POST",self.path,json.dumps(body).encode(),{"Content-Type":"application/json"})
            response=c.getresponse()
            if response.status!=200:
                self.server.note_failure("upstream-http-"+str(response.status))
                stage="downstream"
                self.send_error(502,"Native model upstream rejected request")
                return
            stage="downstream";started=True
            self.send_response(200);self.send_header("Content-Type",response.getheader("Content-Type","application/json"));self.end_headers()
            total=0
            while True:
                stage="upstream-stream"
                chunk=response.read1(16384)
                if not chunk:break
                total+=len(chunk)
                if total>MAX_RESPONSE:raise ValueError("Response exceeds limit")
                stage="downstream"
                self.wfile.write(chunk);self.wfile.flush()
        except (ValueError,OSError,TypeError,KeyError,http.client.HTTPException) as exc:
            if isinstance(exc,TimeoutError):
                code=504
                reason="client-timeout" if stage=="downstream" else "request-timeout" if stage=="request" else "upstream-timeout"
            elif stage=="downstream":
                code=502;reason="client-disconnected"
            elif stage=="request":
                code=422;reason="request-rejected"
            else:
                code=502;reason="upstream-stream-failed" if stage=="upstream-stream" else "upstream-connection-failed"
            self.server.note_failure(reason)
            if not started and stage!="downstream":
                try:self.send_error(code,"Native model "+reason)
                except OSError:pass
        finally:
            if c:c.close()
            self.close_connection=True

def parse_events(raw):
    skills=[];text=[]
    for line in raw.splitlines():
        if not line.strip():continue
        try:event=json.loads(line)
        except ValueError:continue # CLI may print non-event startup notices.
        if not isinstance(event,dict):continue
        if event.get("type")=="error":raise ValueError("Native session reported an error")
        part=event.get("part") or {}
        if event.get("type")=="text" and isinstance(part.get("text"),str):text.append(part["text"])
        if event.get("type")=="tool_use" and part.get("tool")=="skill":
            state=part.get("state") or {}
            name=(state.get("input") or {}).get("id")
            if state.get("status")=="completed" and isinstance(name,str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}",name):skills.append(name)
    output="\n".join(text).strip()
    if not output:raise ValueError("Native session returned no answer")
    return {"text":output[:100000],"skills":sorted(set(skills))}

def qualification_ok(profile,result,hook,calls):
    return bool(calls and result.get("text") and
                (profile=="ponytail" or "brainstorming" in result["skills"]) and
                (profile=="superpowers" or (hook and "ponytail-review" in result["skills"])))

def fixture_prompt(profile):
    skill={"superpowers":"brainstorming","ponytail":"ponytail-review","combined":"brainstorming and ponytail-review"}[profile]
    return ("This is an isolated qualification fixture. Use the native skill tool to load "+skill+
            ". Then provide a short design review of a hypothetical calculator. Do not write files, use shell, ask questions, or perform external actions.")

def run(root,p,prompt,temp_root=None):
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>65536:raise ValueError("Native prompt exceeds limit")
    item,show=model_snapshot(p["endpoint"],p["model"])
    if item["digest"]!=p["model_digest"]:raise ValueError("Model changed; review again")
    name="core-ai-native-execution-"+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="native-",dir=temp_root) as directory:
        path=Path(directory)/"relay.sock"
        with Relay(path,p,item,show) as server:
            path.chmod(0o666) # private parent; container receives only this socket
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with tempfile.TemporaryFile(dir=directory) as out,tempfile.TemporaryFile(dir=directory) as err:
                    try:
                        proc=subprocess.run(["prlimit","--fsize="+str(MAX_RESPONSE),"--",*command(p,name,path)],
                            input=prompt.encode(),stdout=out,stderr=err,timeout=p["timeout"],check=False)
                    except subprocess.TimeoutExpired:
                        raise ValueError("Native task deadline exceeded; relay: "+", ".join(server.diagnostics() or ["no-recorded-error"])) from None
                    if proc.returncode or out.seek(0,os.SEEK_END)>=MAX_RESPONSE:
                        err.seek(max(0,err.seek(0,os.SEEK_END)-16384))
                        detail=err.read().decode("utf-8","replace").lower()
                        tags=[tag for tag in ("native readiness failed","model not found","permission denied","module not found","connection refused","read-only file system","out of memory") if tag in detail]
                        tags.extend(server.diagnostics())
                        raise ValueError("Native CLI failed or output limit reached"+(": "+", ".join(tags) if tags else ""))
                    out.seek(0)
                    try:result=parse_events(out.read().decode("utf-8"))
                    except ValueError as exc:
                        raise ValueError(str(exc)+("; relay: "+", ".join(server.diagnostics()) if server.diagnostics() else "")) from None
                return {**result,"hook_observed":server.hook,"model_calls":server.calls}
            finally:
                try:subprocess.run(["docker","kill",name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
                finally:server.shutdown();thread.join(timeout=5)

def receipts(root):
    folder=manager.safe_path(root,"reports","native-execution")
    if not folder.is_dir():return
    for path in sorted(folder.glob("*.json"),key=lambda x:x.stat().st_mtime,reverse=True)[:200]:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size>256*1024:continue
            record=json.loads(path.read_text())
            if record["approval"]==native_host.digest(record["plan"]) and record.get("qualified") is True:
                yield path.stem,record
        except (OSError,ValueError,KeyError,TypeError):continue

def qualified_plan(root,profile,url,model,mode):
    url=endpoint(url)
    # A socket client cannot initiate requests to an unapproved private address.
    for ident,r in receipts(root):
        p=r["plan"]
        if (p["profile"],p["endpoint"],p["model"],p["mode"])!=(profile,url,model,mode):continue
        current=plan(root,profile,url,model,mode)
        if current==p:return ident,p
    raise ValueError("Native model/profile not qualified; review and qualify on the server")

def execute(root,profile,url,model,mode,prompt,temp_root):
    ident,p=qualified_plan(root,profile,url,model,mode)
    result=run(root,p,prompt,temp_root)
    if not result["model_calls"] or (profile!="superpowers" and not result["hook_observed"]):raise ValueError("Native execution evidence missing")
    return {"profile":profile,"model":model,"mode":mode,"qualification":ident,"provenance":"native-opencode",
            "result":result["text"],"skills":result["skills"],"hook_observed":result["hook_observed"],"model_calls":result["model_calls"]}

def status(root):
    out=[]
    for ident,r in receipts(root):
        p=r["plan"]
        out.append({"profile":p["profile"],"model":p["model"],"mode":p["mode"],"report_id":ident,
                    "state":"qualification-recorded","model_digest":p["model_digest"],"evidence":r["evidence"]})
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    for action in ("review","qualify"):
        q=sub.add_parser(action);q.add_argument("profile",choices=PROFILES);q.add_argument("--endpoint",required=True);q.add_argument("--model",required=True);q.add_argument("--mode",choices=MODES,default="full")
        if action=="qualify":q.add_argument("--approve",required=True)
    sub.add_parser("status")
    a=parser.parse_args()
    if a.action=="status":print(json.dumps(status(a.root),indent=2));return 0
    p=plan(a.root,a.profile,a.endpoint,a.model,a.mode)
    approval=native_host.digest(p)
    if a.action=="review":print(json.dumps(p,indent=2));print("Native execution approval digest:",approval);return 0
    if approval!=a.approve:raise ValueError("Reviewed plan changed")
    result=run(a.root,p,fixture_prompt(a.profile))
    ok=qualification_ok(a.profile,result,result["hook_observed"],result["model_calls"])
    evidence={k:result[k] for k in ("skills","hook_observed","model_calls")}
    record={"plan":p,"approval":approval,"qualified":ok,"evidence":evidence}
    path=manager.safe_path(a.root,"reports","native-execution",uuid.uuid4().hex+".json")
    manager.write_new(path,record)
    print(json.dumps({"profile":a.profile,"model":a.model,"qualified":ok,"report_id":path.stem,**evidence},indent=2))
    return int(not ok)

if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError,http.client.HTTPException) as exc:
        print("STOP:",type(exc).__name__,str(exc) if isinstance(exc,ValueError) else "Check runtime and Ollama connectivity",file=sys.stderr);sys.exit(1)
