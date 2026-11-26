import importlib
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:p=importlib.import_module("package_runtime")
finally:sys.path.pop(0)

class PackageRuntimeTests(unittest.TestCase):
    def test_exact_pins_and_isolated_execution(self):
        manifest=p.manager.load_manifest(p.manager.HERE/"repositories.json")
        with tempfile.TemporaryDirectory() as tmp,patch.object(p.manager,"verify"),patch.object(p,"inspect",return_value={"Id":"sha256:"+"a"*64}):
            root=Path(tmp)
            for name,r in p.RECIPES.items():
                self.assertEqual(manifest[r["repo"]],r["commit"])
                source=p.manager.source(root,r["repo"],r["commit"])
                for entry in r["required"]:
                    path=source/entry;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("fixture")
                plan=p.plan(root,name)
                self.assertIn("RUN --network=none",plan["dockerfile"])
                self.assertIn("locked" if name=="trading-skills" else "frozen-lockfile",plan["dockerfile"])
                cmd=p.container_command(plan,"sha256:"+"b"*64,"fixture")
                self.assertIn("--network=none",cmd);self.assertIn("--read-only",cmd)
                self.assertNotIn("docker.sock",str(cmd));self.assertNotIn("--privileged",cmd)
                with patch.object(p.subprocess,"run") as run:
                    with self.assertRaises(ValueError):p.install(root,name,"wrong")
                    run.assert_not_called()
    def test_unqualified_when_no_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(all(x["state"]=="build-not-qualified" for x in p.evidence(Path(tmp))))
    def test_stdio_round_trip_real_fixture_process(self):
        source="import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n if 'id' in r: print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':{'method':r['method']}}),flush=True)"
        with subprocess.Popen([sys.executable,"-u","-c",source],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
            try:
                peer=p.Stdio(proc,3)
                self.assertEqual(peer.request("initialize",{})["method"],"initialize")
                peer.send({"jsonrpc":"2.0","method":"notifications/initialized"})
                self.assertEqual(peer.request("tools/list",{})["method"],"tools/list")
            finally:
                proc.stdin.close();proc.wait(timeout=3)
if __name__=="__main__":unittest.main()
