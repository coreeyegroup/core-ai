import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
import native_execution as n

class NativeExecutionTest(unittest.TestCase):
    def test_endpoint_is_private_and_canonical(self):
        self.assertEqual(n.endpoint("http://10.8.0.2:11434/"),"http://10.8.0.2:11434")
        for bad in ("https://10.8.0.2:11434","http://8.8.8.8","http://localhost:11434","http://10.0.0.1/a","http://user:secret@10.0.0.1"):
            with self.assertRaises(ValueError): n.endpoint(bad)

    def test_only_selected_model_and_paths(self):
        for method,path,body in (
            ("POST","/api/pull",{"model":"local"}),
            ("POST","/v1/chat/completions",{"model":"other"}),
            ("POST","/api/show",{"model":"other"}),
            ("GET","/api/tags?x=1",None),
            ("POST","/api/delete",{"model":"local"}),
        ):
            with self.assertRaises(ValueError): n.validate_request(method,path,body,"local")
        n.validate_request("GET","/api/tags",None,"local")
        n.validate_request("POST","/v1/chat/completions",{"model":"local","messages":[]},"local")

    def test_real_tool_events_not_plain_model_claims(self):
        events=[{"type":"text","part":{"text":"I loaded brainstorming"}},
                {"type":"tool_use","part":{"tool":"skill","state":{"status":"completed","input":{"name":"brainstorming"}}}},
                {"type":"tool_use","part":{"tool":"skill","state":{"status":"completed","input":{"name":"ponytail-review"}}}}]
        result=n.parse_events("\n".join(json.dumps(x) for x in events))
        self.assertEqual(result["skills"],["brainstorming","ponytail-review"])
        self.assertFalse(n.qualification_ok("combined",result,False,1))
        self.assertTrue(n.qualification_ok("combined",result,True,1))
        self.assertFalse(n.qualification_ok("superpowers",n.parse_events(json.dumps(events[0])),False,1))
        with self.assertRaises(ValueError): n.parse_events(json.dumps({"type":"error"}))

if __name__=="__main__": unittest.main()
