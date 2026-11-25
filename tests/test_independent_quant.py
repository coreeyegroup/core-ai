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
            compile(p["steps"][0][3]+p["steps"][0][4],"<recipe>","exec")
            self.assertIn("--network=none",q.manager.docker_args(Path("/tmp/source"),p,"test"))
            self.assertEqual(recipe["runtime"],q.PYTHON if name in ("technical-indicators","monte-carlo") else q.QUANT)
    def test_loader_preserves_module_identity(self):
        import subprocess
        import json
        with tempfile.TemporaryDirectory() as tmp:
            module=Path(tmp)/"fixture.py"
            module.write_text("import sys\ndef sma(x,n):\n    assert sys.modules[__name__].sma is sma\n    return [None,None,2,3,4]\nema=sma\ndef rsi(x,n):\n    return [None,None,None,100,100]\n")
            step=q.plan("technical-indicators",IMAGE)["steps"][0][:]
            step[0]=sys.executable
            step[5]=str(module)
            result=subprocess.run(step,check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(result.stdout)["rsi"][-1],100)
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
