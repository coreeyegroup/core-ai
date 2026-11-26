import importlib
from pathlib import Path
import sys
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    profiles=importlib.import_module("native_profiles")
finally:
    sys.path.pop(0)

class NativeProfilesTest(unittest.TestCase):
    def test_registration_requires_plugin_and_skills(self):
        expected={"brainstorming"}
        self.assertFalse(profiles.registered([],["brainstorming"],"superpowers",expected))
        self.assertFalse(profiles.registered(["superpowers"],[],"superpowers",expected))
        self.assertTrue(profiles.registered(["superpowers"],["brainstorming"],"superpowers",expected))
    def test_profile_pin_and_container_isolation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(profiles.manager,"verify"),patch.object(profiles.native_host,"inspect_image",return_value=("sha256:"+"a"*64,"2.4.1")):
            root=Path(tmp)
            cfg=profiles.PROFILES["superpowers"]
            source=profiles.manager.source(root,cfg["repo"],cfg["commit"])
            (source/"skills"/"brainstorming").mkdir(parents=True)
            (source/"skills"/"brainstorming"/"SKILL.md").write_text("fixture")
            (source/"index.js").write_text("export default {}")
            p=profiles.plan(root,"superpowers","discovery")
            args=profiles.command(p,"fixture")
            for flag in ("--network=none","--read-only","--cap-drop=ALL","--pull=never"):
                self.assertIn(flag,args)
            self.assertIn("1000:1000",args)
            self.assertIn("type=bind,src="+str(source)+",dst=/plugin,readonly",args)
            self.assertEqual(p["expected_skills"],["brainstorming"])
            self.assertIn("export { default }",p["loader"])
            self.assertNotIn("docker.sock",str(args))
    def test_api_evidence_handles_non_list(self):
        with self.assertRaises(ValueError):profiles.identifiers('{"data":{}}')
        self.assertEqual(profiles.identifiers('{"data":[{"id":"x"},{"id":"y"},{"secret":"ignore"}]}'),["x","y"])
    @unittest.skipUnless(shutil.which("node"),"Node runtime required for polling fixture")
    def test_cold_inventory_waits_and_rejects_failed_plugin(self):
        path=Path(profiles.__file__).with_name("native_probe.mjs").resolve().as_uri()
        source="""
import assert from 'node:assert/strict';
import {observe} from %s;
let ticks=0;
const location={directory:'/workspace'};
const read=async p=>p==='/api/info'?{version:'2.4.1'}:p==='/api/plugin'?{location,data:ticks<1?[]:[{id:'superpowers',state:{status:ticks<2?'failed':'active'}}]}:{location,data:ticks<2?[]:[{id:'brainstorming'}]};
const result=await observe(read,'superpowers',['brainstorming'],{timeout:100,interval:1,now:()=>ticks,sleep:async()=>{ticks++}});
assert.equal(result.attempts,3);
assert.deepEqual(result.plugins,['superpowers']);
assert.deepEqual(result.skills,['brainstorming']);
ticks=0;
const failed=await observe(async p=>p==='/api/info'?{version:'2.4.1'}:p==='/api/plugin'?{location,data:[{id:'superpowers',state:{status:'failed',error:'module not found'}}]}:{location,data:[{id:'brainstorming'}]},'superpowers',['brainstorming'],{timeout:3,interval:1,now:()=>ticks,sleep:async()=>{ticks++}});
assert.deepEqual(failed.plugins,[]);
assert.equal(failed.failed[0].diagnostics[0],'module not found');
""" % __import__("json").dumps(path)
        subprocess.run(["node","--input-type=module","-e",source],check=True,timeout=10)
if __name__=="__main__":unittest.main()
