#!/usr/bin/env python3
"""Private, allowlisted execution bridge. Independent of CORE-AI and its database."""
import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import resource
import socketserver
import subprocess
import tempfile
import threading
import time
import uuid

import batch_install as batch
import manager

MAX_FILE=4*1024*1024
MAX_OUTPUT=6*1024*1024
MAX_FRAME=10*1024*1024
SOCKET="/run/core-ai-lab/gateway.sock"
RUN_SLOT=threading.BoundedSemaphore(1)
REQUEST_SLOTS=threading.BoundedSemaphore(4)

class Busy(ValueError):
    pass

def entry(name):
    for key,tag,module in batch.catalog():
        if key==name:
            return tag,module
    raise ValueError("Unknown reviewed program")

def metadata(name,tag,module):
    plan=batch.plan_for(module,name,"sha256:"+"0"*64)
    r=module.RECIPES[name]
    ext=[]
    if module is batch.docs:
        ext=sorted(r[1])
        fields="Upload one supported document"
        example=[]
    elif module is batch.programs:
        fields="Design query, project name"
        example=["compact institutional AI workspace","CORE-AI"]
    elif module in (batch.trading,batch.quant):
        fields=r["fields"]
        example=r["fixture"]
    elif module is batch.more:
        fields=r[2]
        example=r[3]
    elif module is batch.research:
        fields={"research-mock":"Topic (offline fixture data only)",
                "knowledge-graph-merge":"Array of graph batches with nodes and edges",
                "diagram-prism":"Width, depth, height, corner radius",
                "ml4t-chapter-map":"No arguments"}[name]
        example=r[2]
    else:
        raise ValueError("Recipe has no gateway adapter")
    return {"id":name,"repository":plan["repo"],"commit":plan["commit"],
            "runtime":tag,"fields":fields,"example":example,"extensions":ext,
            "output_file":name in batch.docs.EDIT_RECIPES or name=="notebook-scaffold",
            "mode":"mock" if name=="research-mock" else "offline",
            "state":"pending"}

def catalog(root):
    pins=manager.load_manifest(manager.HERE/"repositories.json")
    rows={repo:{"repository":repo,"commit":commit,"source_present":False,"recipes":[],
                "coverage":"not-reviewed-for-installation"} for repo,commit in pins.items()}
    for repo,row in rows.items():
        try:
            manager.verify(manager.source(root,repo,row["commit"]),row["commit"])
            row["source_present"]=True
        except (ValueError,OSError,subprocess.SubprocessError):
            pass
    images={}
    programs=[]
    for name,tag,module in batch.catalog():
        item=metadata(name,tag,module)
        row=rows[item["repository"]]
        row["coverage"]="partial-reviewed-recipes"
        try:
            if tag not in images: images[tag]=batch.image_id(tag)
            image=images[tag]
            if row["source_present"] and row["commit"]==item["commit"] and batch.verified_receipt(module,root,name,image):
                item["state"]="qualified-receipt"
                item["image"]=image
        except (ValueError,OSError,subprocess.SubprocessError):
            item["state"]="review-required"
        row["recipes"].append(name)
        programs.append(item)
    return {"schema":1,"programs":programs,"repositories":list(rows.values())}

def decode_file(value):
    if not isinstance(value,str) or len(value)>((MAX_FILE+2)//3)*4:
        raise ValueError("Input file exceeds 4 MiB")
    try:
        data=base64.b64decode(value,validate=True)
    except (ValueError,binascii.Error):
        raise ValueError("Invalid file encoding") from None
    if not 0<len(data)<=MAX_FILE: raise ValueError("Input file exceeds 4 MiB or is empty")
    return data

def prepare(root,name,values,extension,file_data,work,container):
    tag,module=entry(name)
    image=batch.image_id(tag)
    qualified=batch.plan_for(module,name,image)
    repo,commit=qualified["repo"],qualified["commit"]
    if manager.load_manifest(manager.HERE/"repositories.json").get(repo)!=commit:
        raise ValueError("Recipe pin differs from manifest")
    source=manager.source(root,repo,commit)
    manager.verify(source,commit)
    if not batch.verified_receipt(module,root,name,image):
        raise ValueError("Exact source and image are not qualified")
    if not isinstance(values,list) or len(json.dumps(values,allow_nan=False))>40000:
        raise ValueError("Expected a bounded JSON parameter array")
    if module is batch.docs:
        if values or extension not in module.RECIPES[name][1]:
            raise ValueError("Select one supported document and no JSON arguments")
        path=work/("input"+extension)
        path.write_bytes(decode_file(file_data))
        path.chmod(0o644)
        plan,args=module.command(root,name,image,path,container)
    else:
        if extension is not None or file_data is not None:
            raise ValueError("This program does not accept a file")
        if module is batch.programs:
            if len(values)!=2 or not all(isinstance(x,str) and 0<len(x)<=500 and x.strip() for x in values):
                raise ValueError("Supply a design query and project name")
            plan=module.plan(name,image,*values,smoke=True)
        else:
            plan=module.plan(name,image,values)
        args=manager.docker_args(source,plan,container)
    if plan["repo"]!=repo or plan["commit"]!=commit or plan["image"]!=image:
        raise ValueError("Execution plan differs from qualified source or image")
    return plan,args

def execute(root,request,temp_root):
    if set(request)!={"action","recipe","values","extension","file_data"}:
        raise ValueError("Unexpected execution request fields")
    name=request["recipe"]
    if not isinstance(name,str): raise ValueError("Expected a reviewed recipe ID")
    if not RUN_SLOT.acquire(blocking=False):
        raise Busy("Execution slot is busy; retry after the current run")
    ident=uuid.uuid4().hex
    container="core-ai-lab-gateway-"+ident
    start=time.monotonic()
    plan=None
    record={"id":ident,"recipe":name,"state":"failed"}
    try:
        with tempfile.TemporaryDirectory(dir=temp_root,prefix="job-") as directory:
            work=Path(directory)
            plan,args=prepare(root,name,request["values"],request["extension"],request["file_data"],work,container)
            record.update(repo=plan["repo"],commit=plan["commit"],image=plan["image"])
            # prlimit bounds output files without unsafe preexec_fn in threaded server.
            with tempfile.TemporaryFile(dir=work) as out, tempfile.TemporaryFile(dir=work) as err:
                try:
                    proc=subprocess.run(["prlimit","--fsize="+str(MAX_OUTPUT+1),"--",*args],
                        stdout=out,stderr=err,timeout=plan["timeout"],check=False)
                except subprocess.TimeoutExpired:
                    record["state"]="timeout"
                    raise ValueError("Program timed out") from None
                record["exit_code"]=proc.returncode
                if proc.returncode!=0:
                    raise ValueError("Program returned nonzero exit status; see execution record")
                if out.seek(0,os.SEEK_END)>MAX_OUTPUT:
                    raise ValueError("Program output exceeds the gateway limit")
                out.seek(0)
                file=None
                if name in batch.docs.EDIT_RECIPES:
                    dest=work/("result"+request["extension"])
                    batch.docs.publish_output(out,dest,name)
                    raw=dest.read_bytes()
                    file={"name":dest.name,"data":base64.b64encode(raw).decode("ascii")}
                    result={"message":"New document generated; original preserved"}
                else:
                    raw=out.read()
                    decoded=raw.decode("utf-8")
                    try:
                        result=json.loads(decoded)
                    except json.JSONDecodeError:
                        result={"text":decoded}
                    if name=="notebook-scaffold":
                        if not isinstance(result,dict) or not isinstance(result.get("cells"),list) or not isinstance(result.get("nbformat"),int):
                            raise ValueError("Invalid notebook output")
                        file={"name":"result.ipynb","data":base64.b64encode(raw).decode("ascii")}
                        result={"message":"Notebook generated; cells were not executed"}
                record["state"]="succeeded"
                return {"id":ident,"state":"succeeded","recipe":name,"repository":plan["repo"],
                        "commit":plan["commit"],"image":plan["image"],"result":result,"file":file,
                        "provenance":"mock-fixtures-not-live-research" if name=="research-mock" else "offline-program"}
    finally:
        try:
            if plan is not None and record["state"]!="succeeded":
                subprocess.run(["docker","kill",container],timeout=15,check=False,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if plan is not None:
                record["duration_seconds"]=round(time.monotonic()-start,3)
                manager.write_new(manager.safe_path(root,"reports","gateway",ident+".json"),record)
        finally:
            RUN_SLOT.release()

def route(root,request,temp_root):
    if not isinstance(request,dict): raise ValueError("Expected an object")
    if request=={"action":"catalog"}: return catalog(root)
    if request.get("action")=="run": return execute(root,request,temp_root)
    raise ValueError("Unknown gateway action")

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(20)
        try:
            data=self.rfile.readline(MAX_FRAME+1)
            if len(data)>MAX_FRAME or not data.endswith(b"\n"):
                raise ValueError("Request too large or incomplete")
            request=json.loads(data)
            response={"ok":True,"data":route(self.server.root,request,self.server.temp_root)}
        except Busy as exc:
            response={"ok":False,"code":"busy","error":str(exc)}
        except (ValueError,UnicodeError,KeyError,TypeError,OverflowError) as exc:
            # Input or dependency errors may contain user data or filesystem details.
            response={"ok":False,"code":"rejected","error":"Program request rejected or execution failed. Verify inputs, qualification and lab reports."}
        except (OSError,subprocess.SubprocessError):
            response={"ok":False,"code":"unavailable","error":"Lab runtime unavailable. Check its service and image."}
        payload=json.dumps(response,ensure_ascii=True,allow_nan=False).encode()+b"\n"
        if len(payload)>MAX_FRAME:
            payload=b'{"ok":false,"code":"rejected","error":"Response exceeds the gateway limit"}\n'
        try:
            self.wfile.write(payload)
        except OSError:
            pass

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    request_queue_size=4
    def process_request(self,request,address):
        if not REQUEST_SLOTS.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request,address)
        except BaseException:
            REQUEST_SLOTS.release()
            raise
    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: REQUEST_SLOTS.release()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    parser.add_argument("--socket",type=Path,default=Path(SOCKET))
    parser.add_argument("--catalog",action="store_true")
    a=parser.parse_args()
    if a.catalog:
        print(json.dumps(catalog(a.root),indent=2))
        return
    root=a.root.resolve(strict=True)
    if a.socket.exists() or a.socket.is_symlink():
        raise ValueError("Socket path already exists; inspect the service, do not replace it")
    # Service manager owns the private parent directory; no public TCP listener.
    os.umask(0o077)
    with Server(str(a.socket),Handler) as server:
        server.root=root
        server.temp_root=a.socket.parent
        a.socket.chmod(0o660)
        server.serve_forever()

if __name__=="__main__":
    main()
