import json
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import tempfile
import threading
import time
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
import native_execution as n

class NativeExecutionTest(unittest.TestCase):
    def test_endpoint_is_private_and_canonical(self):
        self.assertEqual(n.endpoint("http://10.8.0.2:11434/"),"http://10.8.0.2:11434")
        for bad in ("https://10.8.0.2:11434","http://8.8.8.8","http://localhost:11434","http://10.0.0.1/a","http://user:secret@10.0.0.1"):
            with self.assertRaises(ValueError): n.endpoint(bad)

    def test_disposable_plan_disables_only_background_title_agent(self):
        def source(root,profile,route):
            return {"profile":profile,"source":"/fixture/"+profile,"repo":"fixture/"+profile,
                    "commit":"abc","expected_skills":["fixture"],"image":"fixture-image","version":"2.4.1"}
        with patch.object(n.native_profiles,"plan",side_effect=source), patch.object(n,"model_snapshot",return_value=({"digest":"fixture"},{})):
            for profile in ("superpowers","ponytail","combined"):
                p=n.plan(Path("/fixture"),profile,"http://127.0.0.1:11434","local","full")
                self.assertEqual(p["config"].get("agents"),{"title":{"disabled":True}})
                self.assertEqual(len(p["config"]["plugins"]),2 if profile=="combined" else 1)
                args=n.command(p,"fixture","/fixture/relay.sock")
                config=next(x for x in args if x.startswith("NATIVE_CONFIG="))
                self.assertEqual(json.loads(config.split("=",1)[1]),p["config"])

    def test_operator_timeout_bounds(self):
        with patch.dict(n.os.environ,{"CORE_AI_NATIVE_TASK_SECONDS":"480","CORE_AI_NATIVE_INFERENCE_SECONDS":"240"}):
            self.assertEqual(n.timeout_settings(),(480,240))
        for task,inference in (("540","301"),("541","240"),("180","180"),("bad","240")):
            with patch.dict(n.os.environ,{"CORE_AI_NATIVE_TASK_SECONDS":task,"CORE_AI_NATIVE_INFERENCE_SECONDS":inference}):
                with self.assertRaises(ValueError):n.timeout_settings()

    def test_only_selected_model_and_paths(self):
        for method,path,body in (
            ("POST","/api/pull",{"model":"local"}),
            ("POST","/v1/chat/completions",{"model":"other"}),
            ("POST","/api/show",{"model":"other"}),
            ("GET","/api/tags?x=1",None),
            ("POST","/api/delete",{"model":"local"}),
        ):
            with self.assertRaises(ValueError): n.validate_request(method,path,body,"local")
        n.validate_request("GET","/api/tags",None,"local")
        n.validate_request("POST","/v1/chat/completions",{"model":"local","messages":[]},"local")

    def test_real_tool_events_not_plain_model_claims(self):
        events=[{"type":"text","part":{"text":"I loaded brainstorming"}},
                {"type":"tool_use","part":{"tool":"skill","state":{"status":"completed","input":{"id":"brainstorming"}}}},
                {"type":"tool_use","part":{"tool":"skill","state":{"status":"completed","input":{"id":"ponytail-review"}}}}]
        result=n.parse_events("\n".join(json.dumps(x) for x in events))
        self.assertEqual(result["skills"],["brainstorming","ponytail-review"])
        self.assertFalse(n.qualification_ok("combined",result,False,1))
        self.assertTrue(n.qualification_ok("combined",result,True,1))
        self.assertFalse(n.qualification_ok("superpowers",n.parse_events(json.dumps(events[0])),False,1))
        with self.assertRaises(ValueError): n.parse_events(json.dumps({"type":"error"}))

    def test_socket_relay_filters_and_observes_actual_model_request(self):
        requests=[];progress=[]
        class Model(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path,body,self.headers.get("Authorization")))
                if body.get("messages")==[{"role":"user","content":"reject"}]:
                    self.send_error(503,"fixture-private-detail");return
                if body.get("messages")==[{"role":"user","content":"slow"}]:
                    time.sleep(0.35)
                    try:
                        self.send_response(200)
                        self.end_headers()
                    except OSError:pass
                    return
                self.send_response(200)
                self.send_header("Content-Type","text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: [DONE]\n\n")
        with HTTPServer(("127.0.0.1",0),Model) as provider,tempfile.TemporaryDirectory() as d:
            t=threading.Thread(target=provider.serve_forever,daemon=True);t.start()
            p={"endpoint":"http://127.0.0.1:"+str(provider.server_port),"model":"local","mode":"full","inference_timeout":0.1}
            path=Path(d)/"relay.sock"
            with n.Relay(path,p,{"model":"local"},{"capabilities":["tools","completion"]},progress=progress.append) as relay:
                thread=threading.Thread(target=relay.serve_forever,daemon=True);thread.start()
                class UnixConnection(http.client.HTTPConnection):
                    def connect(self):
                        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                        self.sock.settimeout(5);self.sock.connect(str(path))
                def call(method,route,body=None):
                    conn=UnixConnection("localhost",timeout=5)
                    try:
                        conn.request(method,route,None if body is None else json.dumps(body).encode(),
                                     {"Content-Type":"application/json","Authorization":"Bearer fixture-not-forwarded"})
                        resp=conn.getresponse()
                        return resp.status,resp.read()
                    finally:conn.close()
                try:
                    self.assertEqual(json.loads(call("GET","/api/tags")[1]),{"models":[{"model":"local"}]})
                    self.assertEqual(call("POST","/api/pull",{"model":"local"})[0],422)
                    self.assertEqual(call("POST","/v1/chat/completions",{"model":"wrong","messages":[]})[0],422)
                    self.assertEqual(requests,[])
                    status,raw=call("POST","/v1/chat/completions",{"model":"local","max_tokens":9000,
                        "messages":[{"role":"system","content":"PONYTAIL MODE ACTIVE — level: full"}]})
                    self.assertEqual((status,raw),(200,b"data: [DONE]\n\n"))
                    self.assertEqual(requests[0][1]["max_tokens"],4096)
                    self.assertIsNone(requests[0][2])
                    self.assertEqual(relay.calls,1)
                    self.assertTrue(relay.hook)
                    self.assertTrue(any(x["event"]=="model-request" and x["call"]==1 and x["tools"]==0 and x["max_tokens"]==4096 for x in progress))
                    self.assertTrue(any(x["event"]=="upstream-headers" and x["status"]==200 for x in progress))
                    self.assertNotIn("PONYTAIL MODE ACTIVE",json.dumps(progress))
                    self.assertNotIn("fixture-not-forwarded",json.dumps(progress))
                    rejected=call("POST","/v1/chat/completions",{"model":"local","messages":[{"role":"user","content":"reject"}]})
                    self.assertEqual(rejected[0],502)
                    self.assertNotIn(b"fixture-private-detail",rejected[1])
                    slow=call("POST","/v1/chat/completions",{"model":"local","messages":[{"role":"user","content":"slow"}]})
                    self.assertEqual(slow[0],504)
                    self.assertIn("upstream-http-503",relay.diagnostics())
                    self.assertIn("upstream-timeout",relay.diagnostics())
                finally:
                    relay.shutdown();thread.join(timeout=5)
                    provider.shutdown();t.join(timeout=5)

if __name__=="__main__": unittest.main()
