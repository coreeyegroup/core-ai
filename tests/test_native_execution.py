import json
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import tempfile
import threading
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
import native_execution as n

class NativeExecutionTest(unittest.TestCase):
    def test_endpoint_is_private_and_canonical(self):
        self.assertEqual(n.endpoint("http://10.8.0.2:11434/"),"http://10.8.0.2:11434")
        for bad in ("https://10.8.0.2:11434","http://8.8.8.8","http://localhost:11434","http://10.0.0.1/a","http://user:secret@10.0.0.1"):
            with self.assertRaises(ValueError): n.endpoint(bad)

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
        requests=[]
        class Model(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path,body,self.headers.get("Authorization")))
                self.send_response(200)
                self.send_header("Content-Type","text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: [DONE]\n\n")
        with HTTPServer(("127.0.0.1",0),Model) as provider,tempfile.TemporaryDirectory() as d:
            t=threading.Thread(target=provider.serve_forever,daemon=True);t.start()
            p={"endpoint":"http://127.0.0.1:"+str(provider.server_port),"model":"local","mode":"full"}
            path=Path(d)/"relay.sock"
            with n.Relay(path,p,{"model":"local"},{"capabilities":["tools","completion"]}) as relay:
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
                finally:
                    relay.shutdown();thread.join(timeout=5)
                    provider.shutdown();t.join(timeout=5)

if __name__=="__main__": unittest.main()
