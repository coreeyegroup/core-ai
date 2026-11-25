#!/usr/bin/env python3
"""MCP stdio bridge for CORE-AI scoped offline program jobs (2025-11-25 lifecycle)."""
import argparse
import http.client
import json
import os
import sys
import time
from urllib.parse import urlsplit
import uuid

MAX_LINE=256*1024
MAX_RESPONSE=10*1024*1024
VERSIONS={"2024-11-05","2025-03-26","2025-06-18","2025-11-25"}

class Api:
    def __init__(self,origin,token):
        parsed=urlsplit(origin)
        if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("","/"):
            raise ValueError("Configure a trusted HTTPS origin without path or credentials.")
        if not token.startswith("coreai_") or len(token)!=50:raise ValueError("Set a valid scoped connection key in CORE_AI_PROGRAM_API_TOKEN.")
        self.host=parsed.hostname;self.port=parsed.port or 443;self.token=token
    def request(self,method,path,body=None):
        conn=http.client.HTTPSConnection(self.host,self.port,timeout=45)
        try:
            conn.request(method,"/api/v1/automation/programs"+path,
                         body=json.dumps(body,allow_nan=False) if body is not None else None,
                         headers={"Authorization":"Bearer "+self.token,"Content-Type":"application/json","Accept":"application/json"})
            response=conn.getresponse()
            if not 200<=response.status<300:raise ValueError("Scoped API request rejected ("+str(response.status)+").")
            raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise ValueError("API response exceeds limit.")
            return json.loads(raw)
        finally:conn.close()

class Bridge:
    def __init__(self,api,allow,wait_seconds=180):
        self.api=api;self.allow=set(allow);self.wait_seconds=wait_seconds;self.initialized=False
    def list_programs(self):
        return {p["id"]:p for p in self.api.request("GET","")["programs"] if p["id"] in self.allow}
    def tool_list(self):
        return {"tools":[{"name":name,"description":"Offline CORE-AI program: "+name+
            ". Mode: "+p["mode"]+". Parameters: "+json.dumps(p["fields"])+"; example: "+json.dumps(p["example"]),
            "inputSchema":{"type":"object","properties":{"values":{"type":"array"}},"required":["values"],"additionalProperties":False}}
            for name,p in self.list_programs().items()]}
    def call(self,params):
        if set(params)!={"name","arguments"} or params["name"] not in self.allow:
            raise ValueError("Tool not allowed.")
        name=params["name"];args=params["arguments"]
        if not isinstance(args,dict) or set(args)!={"values"} or not isinstance(args["values"],list):
            raise ValueError("Expected a values array.")
        if name not in self.list_programs():raise ValueError("Tool no longer permitted.")
        ident=self.api.request("POST","/jobs",{"recipe":name,"values":args["values"],"request_id":str(uuid.uuid4())})["id"]
        ident=str(uuid.UUID(ident))
        end=time.monotonic()+self.wait_seconds
        while time.monotonic()<end:
            row=self.api.request("GET","/jobs/"+ident)
            if row["status"] in ("SUCCEEDED","FAILED","CANCELLED"):
                text=json.dumps({"job_id":ident,"status":row["status"],"result":row.get("result"),"error":row.get("error")},ensure_ascii=False)
                return {"content":[{"type":"text","text":text[:100000]}],"isError":row["status"]!="SUCCEEDED"}
            time.sleep(.5)
        return {"content":[{"type":"text","text":"Job remains queued or active. Inspect CORE-AI job "+ident+"; do not resubmit automatically."}],"isError":True}
    def handle(self,req):
        ident=req.get("id")
        def response(result=None,error=None):
            return {"jsonrpc":"2.0","id":ident,**({"error":error} if error else {"result":result})}
        if req.get("jsonrpc")!="2.0" or not isinstance(req.get("method"),str):
            return response(error={"code":-32600,"message":"Invalid request"})
        method=req["method"];params=req.get("params",{})
        if not isinstance(params,dict):return response(error={"code":-32602,"message":"Invalid params"})
        if "id" not in req:
            if method=="notifications/initialized":self.initialized=True
            return None
        if method=="initialize":
            requested=params.get("protocolVersion")
            return response({"protocolVersion":requested if requested in VERSIONS else "2025-11-25",
                "capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"core-ai-programs","version":"1.0.0"}})
        if method=="ping":return response({})
        if not self.initialized:return response(error={"code":-32002,"message":"Initialize first"})
        try:
            if method=="tools/list":return response(self.tool_list())
            if method=="tools/call":
                try:return response(self.call(params))
                except (ValueError,OSError,http.client.HTTPException,KeyError,TypeError):
                    return response({"content":[{"type":"text","text":"Scoped program execution rejected or unavailable. Inspect CORE-AI history."}],"isError":True})
            return response(error={"code":-32601,"message":"Method not found"})
        except (ValueError,OSError,http.client.HTTPException,KeyError,TypeError):
            return response(error={"code":-32000,"message":"Scoped CORE-AI API unavailable"})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origin",required=True)
    p.add_argument("--allow",action="append",required=True)
    p.add_argument("--wait-seconds",type=int,default=180)
    a=p.parse_args()
    if not 5<=a.wait_seconds<=600:raise SystemExit("Invalid wait budget.")
    try:b=Bridge(Api(a.origin,os.environ.get("CORE_AI_PROGRAM_API_TOKEN","")),a.allow,a.wait_seconds)
    except ValueError as exc:raise SystemExit(str(exc))
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line:return
        if len(line)>MAX_LINE or not line.endswith(b"\n"):raise SystemExit("Invalid or oversized MCP frame.")
        try:
            request=json.loads(line)
            result=b.handle(request) if isinstance(request,dict) else {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid request"}}
        except (ValueError,TypeError):
            result={"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Parse error"}}
        if result is not None:print(json.dumps(result,ensure_ascii=True,allow_nan=False),flush=True)
if __name__=="__main__":main()
