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
    tools=importlib.import_module("research_programs")
finally:
    sys.path.pop(0)
IMAGE="sha256:"+"a"*64

class ResearchTests(unittest.TestCase):
    def test_pins_and_compilation(self):
        pins=tools.manager.load_manifest(tools.manager.HERE/"repositories.json")
        for name in tools.RECIPES:
            p=tools.plan(name,IMAGE)
            self.assertEqual(p["commit"],pins[p["repo"]])
            step=p["steps"][0]
            compile(step[2],"<launcher>","exec")
            compile(step[3]+step[4],"<recipe>","exec")
            self.assertIn("--network=none",tools.manager.docker_args(Path("/tmp/source"),p,"test"))
    def test_invalid_inputs(self):
        for name,a in [("research-mock",["--publish"]),("knowledge-graph-merge",[]),("diagram-prism",[0,20,10,0]),("ml4t-chapter-map",[1])]:
            with self.assertRaises(ValueError): tools.plan(name,IMAGE,a)
    def test_launcher_and_graph_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"fixture.py"
            source.write_text("def merge_and_normalize(batches):\n    return {'nodes':[{'id':'file:a.py','complexity':'simple'},{'id':'file:b.py','complexity':'moderate'}],'edges':[{'source':'file:a.py','target':'file:b.py'}]}, ['duplicate node IDs removed']\n")
            step=tools.plan("knowledge-graph-merge",IMAGE)["steps"][0][:]
            step[0]=sys.executable
            step[5]=str(source)
            result=subprocess.run(step,check=True,capture_output=True,text=True)
            self.assertEqual(len(json.loads(result.stdout)["graph"]["nodes"]),2)
    def test_mock_cli_requires_research_only_for_no_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"fixture.py"
            source.write_text(
                "import sys,json\n"
                "if '--no-research-persistence' in sys.argv and '--research-only' not in sys.argv:\n"
                "    sys.exit(2)\n"
                "assert '--mock' in sys.argv and '--no-browser-cookies' in sys.argv\n"
                "assert '--no-research-persistence' in sys.argv\n"
                "print(json.dumps({'schema_version':'1.4','query':sys.argv[1],"
                "'results':[],'clusters':[],'source_status':{}}))\n")
            step=tools.plan("research-mock",IMAGE)["steps"][0][:]
            step[0]=sys.executable
            step[5]=str(source)
            result=subprocess.run(step,check=True,capture_output=True,text=True)
            data=json.loads(result.stdout)
            self.assertEqual(data["provenance"],"mock-fixtures-not-live-research")
            self.assertEqual(data["report"]["query"],"test topic")
    def test_failed_run_no_receipt_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(tools.manager,"run_plan") as run:
            root=Path(tmp)
            name="research-mock"
            with self.assertRaises(ValueError): tools.install(root,name,IMAGE,"bad")
            run.assert_not_called()
            p=tools.plan(name,IMAGE)
            approval=tools.manager.digest(p)
            run.return_value=1
            self.assertEqual(tools.install(root,name,IMAGE,approval),1)
            self.assertFalse(tools.receipt(root,name,IMAGE)[0].exists())
            run.return_value=0
            self.assertEqual(tools.install(root,name,IMAGE,approval),0)
            self.assertEqual(tools.install(root,name,IMAGE,approval),0)
            self.assertEqual(run.call_count,2)
            self.assertEqual(tools.run(root,name,IMAGE,["agent workflows"]),0)
if __name__=="__main__":
    unittest.main()
