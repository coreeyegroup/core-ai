import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    g=importlib.import_module("gateway")
finally:
    sys.path.pop(0)

IMAGE="sha256:"+"a"*64

class GatewayTests(unittest.TestCase):
    def test_catalog_covers_all_reviewed_recipes(self):
        rows=[g.metadata(n,t,m) for n,t,m in g.batch.catalog()]
        self.assertEqual(len(rows),38)
        self.assertEqual(len({r["id"] for r in rows}),len(rows))
        self.assertEqual(sum(bool(r["extensions"]) for r in rows),4)
    def test_unknown_and_unapproved_recipes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaises(ValueError): g.entry("shell")
            with patch.object(g.batch,"image_id",return_value=IMAGE),patch.object(g.manager,"verify"),patch.object(g.batch,"verified_receipt",return_value=False):
                with self.assertRaisesRegex(ValueError,"not qualified"):
                    g.prepare(root,"position-sizing",[10000,.01,100,95,0,0],None,None,root,"test")
    def test_qualified_numeric_and_file_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(g.batch,"image_id",return_value=IMAGE),patch.object(g.manager,"verify"),patch.object(g.batch,"verified_receipt",return_value=True):
                p,args=g.prepare(root,"position-sizing",[10000,.01,100,95,0,0],None,None,root,"test")
                self.assertEqual(p["image"],IMAGE)
                self.assertIn("--network=none",args)
                self.assertIn("--read-only",args)
                p,args=g.prepare(root,"pdf-form-check",[],".pdf","JVBERg==",root,"test")
                self.assertIn("type=bind,src="+str(root/"input.pdf")+",dst=/input.pdf,readonly",args)
                with self.assertRaises(ValueError):
                    g.prepare(root,"pdf-form-check",[],"../../.ssh","JVBERg==",root,"test")
    def test_no_arbitrary_request_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for request in [{"action":"run","command":"id"},{"action":"install"},{"action":"catalog","path":"/"}]:
                with self.assertRaises(ValueError): g.route(root,request,root)
    def test_unix_socket_protocol(self):
        import socket
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            path=root/"gateway.sock"
            with g.Server(str(path),g.Handler) as server:
                server.root=root
                server.temp_root=root
                with patch.object(g,"catalog",return_value={"schema":1,"programs":[],"repositories":[]}):
                    thread=threading.Thread(target=server.serve_forever,daemon=True)
                    thread.start()
                    try:
                        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
                            conn.settimeout(3)
                            conn.connect(str(path))
                            conn.sendall(b'{"action":"catalog"}\n')
                            reply=json.loads(conn.makefile("rb").readline())
                        self.assertTrue(reply["ok"])
                        self.assertEqual(reply["data"]["schema"],1)
                    finally:
                        server.shutdown()
                        thread.join(3)
    def test_result_executes_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p={"repo":"agiprolabs/claude-trading-skills","commit":"981e1d736cdc02bdc1c55c74ec9224e956414706","image":IMAGE,"timeout":120}
            def fake_run(args,stdout=None,**kwargs):
                stdout.write(b'{"units":20}')
                return type("P",(),{"returncode":0})()
            with patch.object(g,"prepare",return_value=(p,["docker","run","test"])),patch.object(g.subprocess,"run",side_effect=fake_run):
                r=g.execute(root,{"action":"run","recipe":"position-sizing","values":[],"extension":None,"file_data":None},root)
            self.assertEqual(r["result"]["units"],20)
            report=json.loads((root/"reports"/"gateway"/(r["id"]+".json")).read_text())
            self.assertEqual(report["state"],"succeeded")
            self.assertNotIn("values",report)
if __name__=="__main__":
    unittest.main()
