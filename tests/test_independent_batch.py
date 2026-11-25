import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    batch=importlib.import_module("batch_install")
    more=batch.more
finally:
    sys.path.pop(0)

IMAGE="sha256:"+"e"*64

class BatchTests(unittest.TestCase):
    def test_all_recipe_plans_and_pins(self):
        pins=batch.manager.load_manifest(batch.manager.HERE/"repositories.json")
        self.assertEqual(len(batch.catalog()),22)
        for name,tag,module in batch.catalog():
            p=batch.plan_for(module,name,IMAGE)
            self.assertEqual(p["commit"],pins[p["repo"]])
            self.assertEqual(p["image"],IMAGE)
            for step in p["steps"]:
                if step[:2]==["python3","-c"]:
                    compile(step[2],"<qualification>","exec")
    def test_approval_and_continue(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(batch,"image_id",return_value=IMAGE), patch.object(batch.manager,"verify"), patch.object(batch,"verified_receipt",return_value=False):
            root=Path(tmp)
            p=batch.reviewed_plan(root)
            with patch.object(batch.programs,"install") as install:
                with self.assertRaises(ValueError): batch.install(root,"wrong")
                install.assert_not_called()
            with patch.object(batch.programs,"install",return_value=1) as ui, patch.object(batch.docs,"install",return_value=1) as docs, patch.object(batch.trading,"install",return_value=1) as trading, patch.object(more,"install",return_value=1) as extra, patch.object(batch.quant,"install",return_value=1) as quant:
                self.assertEqual(batch.install(root,batch.digest(p)),1)
                self.assertEqual(sum(m.call_count for m in (ui,docs,trading,extra,quant)),22)
                report=json.loads(next((root/"reports"/"batches").glob("*.json")).read_text())
                self.assertEqual(len(report["results"]),22)
                self.assertTrue(all(r["state"]=="failed" for r in report["results"]))
    def test_resume_skips_qualified(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(batch,"image_id",return_value=IMAGE), patch.object(batch.manager,"verify"), patch.object(batch,"verified_receipt",return_value=True), patch.object(batch.programs,"install") as ui, patch.object(batch.docs,"install") as docs, patch.object(batch.trading,"install") as trading, patch.object(more,"install") as extra, patch.object(batch.quant,"install") as quant:
            root=Path(tmp)
            self.assertEqual(batch.install(root,batch.digest(batch.reviewed_plan(root))),0)
            for m in (ui,docs,trading,extra,quant): m.assert_not_called()
    def test_image_change_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(batch.manager,"verify"),patch.object(batch,"image_id",return_value=IMAGE) as image:
            root=Path(tmp)
            p=batch.reviewed_plan(root)
            image.return_value="sha256:"+"f"*64
            with self.assertRaises(ValueError): batch.install(root,batch.digest(p))
    def test_invalid_extra_inputs(self):
        for name,a in [("contract-sizing",[100,0,100,95,0,0,1,1]),("equity-drawdown",[0,1]),("option-implied-vol",[1,100,100,1,.05,"invalid",0]),("notebook-scaffold",["experiment","bad\nname"]),("trade-statistics",[float("nan")])]:
            with self.assertRaises(ValueError): more.plan(name,IMAGE,a)

if __name__=="__main__":
    unittest.main()
