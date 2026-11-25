import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    q=importlib.import_module("quant_programs")
finally:
    sys.path.pop(0)

IMAGE="sha256:"+"a"*64
class QuantTests(unittest.TestCase):
    def test_pin_compile_and_runtime(self):
        pins=q.manager.load_manifest(q.manager.HERE/"repositories.json")
        for name,recipe in q.RECIPES.items():
            p=q.plan(name,IMAGE)
            self.assertEqual(p["commit"],pins[p["repo"]])
            compile(p["steps"][0][2],"<fixture>","exec")
            self.assertIn("--network=none",q.manager.docker_args(Path("/tmp/source"),p,"test"))
            self.assertEqual(recipe["runtime"],q.PYTHON if name in ("technical-indicators","monte-carlo") else q.QUANT)
    def test_validation_and_large_payload(self):
        for name,a in [("technical-indicators",[[1,2],3]),("monte-carlo",[[1]*5,100,5,10,10000,7]),("correlation-matrix",[[1,1,1],[2,3,4]]),("numpy-drawdown",[100,0]),("ema-backtest",[10,5,10000,.001,.001,1,42,500,[]]),("scipy-option-price",[100,100,0,.05,.2,0])]:
            with self.assertRaises(ValueError): q.plan(name,IMAGE,a)
        p=q.plan("technical-indicators",IMAGE,[[100.123456789]*500,14])
        self.assertTrue(all(len(x)<=2000 for x in p["steps"][0]))
        self.assertGreater(len(p["steps"][0]),5)
    def test_qualification_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(q.manager,"run_plan",return_value=0) as run:
            root=Path(tmp)
            name="technical-indicators"
            with self.assertRaises(ValueError): q.install(root,name,IMAGE,"wrong")
            run.assert_not_called()
            approval=q.manager.digest(q.plan(name,IMAGE))
            self.assertEqual(q.install(root,name,IMAGE,approval),0)
            self.assertEqual(q.install(root,name,IMAGE,approval),0)
            self.assertEqual(run.call_count,1)
            self.assertEqual(q.run(root,name,IMAGE,[[1,2,3,4],2]),0)
    def test_no_receipt_on_failed_fixture(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(q.manager,"run_plan",return_value=1):
            root=Path(tmp)
            name="ema-backtest"
            self.assertEqual(q.install(root,name,IMAGE,q.manager.digest(q.plan(name,IMAGE))),1)
            self.assertFalse(q.receipt(root,name,IMAGE)[0].exists())
if __name__=="__main__":
    unittest.main()
