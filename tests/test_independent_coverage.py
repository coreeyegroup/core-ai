import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    batch=importlib.import_module("batch_install")
    gateway=importlib.import_module("gateway")
    extra=importlib.import_module("coverage_programs")
finally:
    sys.path.pop(0)
IMAGE="sha256:"+"a"*64

class CoverageTests(unittest.TestCase):
    def test_every_executable_bearing_repository_has_reviewed_recipe(self):
        pins=batch.manager.load_manifest(batch.manager.HERE/"repositories.json")
        plans={batch.plan_for(m,n,IMAGE)["repo"] for n,t,m in batch.catalog()}
        self.assertEqual(set(pins)-plans,{"multica-ai/andrej-karpathy-skills"})
        self.assertEqual(len(extra.RECIPES),12)
        for n,t,m in batch.catalog():
            p=batch.plan_for(m,n,IMAGE)
            self.assertEqual(p["commit"],pins[p["repo"]])
            self.assertEqual(gateway.metadata(n,t,m)["repository"],p["repo"])
    def test_no_arbitrary_arguments_and_no_receipt_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(extra.manager,"run_plan",return_value=1) as run:
            root=Path(tmp)
            with self.assertRaises(ValueError):extra.plan("superpowers-plugin-check",IMAGE,["--force"])
            p=extra.plan("superpowers-plugin-check",IMAGE)
            with self.assertRaises(ValueError):extra.install(root,"superpowers-plugin-check",IMAGE,"wrong")
            run.assert_not_called()
            self.assertEqual(extra.install(root,"superpowers-plugin-check",IMAGE,extra.manager.digest(p)),1)
            self.assertFalse(extra.receipt(root,"superpowers-plugin-check",IMAGE)[0].exists())
    def test_invalid_calculation_input(self):
        for name,params in [("gauss-indicators",[[1,2],3]),("animation-easing",[0,1,2,"linear"]),("dcf-assumption-check",[.03,float("nan")]),("vercel-rate-limit-check",["x"*2001])]:
            with self.assertRaises(ValueError):extra.plan(name,IMAGE,params)
    def test_isolated_runtime_and_python_compilation(self):
        for name in extra.RECIPES:
            plan=extra.plan(name,IMAGE)
            args=extra.manager.docker_args(Path("/tmp/source"),plan,"fixture")
            self.assertIn("--network=none",args)
            self.assertIn("--read-only",args)
            self.assertIn("--user=65534:65534",args)
            for step in plan["steps"]:
                if step[:2]==["python3","-c"]:
                    compile(step[2],"<wrapper>","exec")
if __name__=="__main__":unittest.main()
