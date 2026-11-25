import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    native=importlib.import_module("native_host")
finally:
    sys.path.pop(0)

IMAGE="sha256:"+"a"*64

class NativeHostTests(unittest.TestCase):
    def test_pin_and_isolation(self):
        pins=native.manager.load_manifest(native.manager.HERE/"repositories.json")
        self.assertEqual(pins[native.REPO],native.COMMIT)
        with tempfile.TemporaryDirectory() as tmp,patch.object(native.manager,"verify"),patch.object(native,"inspect_image",return_value=(IMAGE,"2.2.7")):
            p=native.plan(Path(tmp),"test")
            args=native.command(p,["plugin","list"],"probe")
            self.assertIn("--network=none",args)
            self.assertIn("--read-only",args)
            self.assertIn("1000:1000",args)
            self.assertIn("type=bind,src="+p["source"]+",dst=/plugins/superpowers,readonly",args)
            self.assertEqual(args[-2:],["plugin","list"])
            self.assertIn("--entrypoint",args)
            self.assertIn('$XDG_CONFIG_HOME/opencode/opencode.json',p["bootstrap"])
    def test_review_required_before_run(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(native.manager,"verify"),patch.object(native,"inspect_image",return_value=(IMAGE,"2.2.7")),patch.object(native.subprocess,"run") as run:
            with self.assertRaises(ValueError):
                native.verify(Path(tmp),"test","wrong")
            run.assert_not_called()
    def test_probe_does_not_claim_functional_qualification(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(native.manager,"verify"),patch.object(native,"inspect_image",return_value=(IMAGE,"2.2.7")),patch.object(native.subprocess,"run") as run:
            root=Path(tmp)
            p=native.plan(root,"test")
            skill=Path(p["source"])/"skills"/"brainstorming"
            skill.mkdir(parents=True)
            (skill/"SKILL.md").write_text("fixture")
            run.side_effect=[subprocess.CompletedProcess([],0,"2.2.7\n",""),subprocess.CompletedProcess([],0,'{"data":[{"id":"superpowers"}]}',""),subprocess.CompletedProcess([],0,'{"data":[{"id":"brainstorming"}]}',"")]
            self.assertEqual(native.verify(root,"test",native.digest(p)),0)
            self.assertFalse((root/"packages").exists())
            self.assertEqual(len(list((root/"reports"/"native").glob("*.json"))),1)
if __name__=="__main__":
    unittest.main()
