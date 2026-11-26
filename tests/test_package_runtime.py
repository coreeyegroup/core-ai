import importlib
from pathlib import Path
import sys
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
if __name__=="__main__":unittest.main()
