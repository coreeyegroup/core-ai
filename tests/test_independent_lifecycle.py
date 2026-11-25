import importlib
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:
    review=importlib.import_module("installation_review")
    mcp=importlib.import_module("mcp_stdio")
    gateway=importlib.import_module("gateway")
finally:
    sys.path.pop(0)

class LifecycleTests(unittest.TestCase):
    def test_all_pins_have_review_classification(self):
        pins=review.manager.load_manifest(review.manager.HERE/"repositories.json")
        self.assertEqual(set(review.REVIEW),set(pins))
        for name in pins:
            data=review.classify(name,{"files":[],"counts":{}})
            self.assertTrue(data["next_action"])
            self.assertTrue(all(not e["present"] for e in data["entrypoints"]))
    def test_mcp_protocol_and_scoped_execution(self):
        api=Mock()
        ident="a"*8+"-"+"a"*4+"-"+"a"*4+"-"+"a"*4+"-"+"a"*12
        cat={"programs":[{"id":"position-sizing","mode":"offline","fields":["account"],"example":[10000]},
                          {"id":"black-scholes","mode":"offline","fields":[],"example":[]}]}
        api.request.side_effect=[cat,cat,{"id":ident},{"status":"SUCCEEDED","result":{"units":20}}]
        b=mcp.Bridge(api,["position-sizing"])
        req=lambda method,params={}:{"jsonrpc":"2.0","id":1,"method":method,"params":params}
        self.assertEqual(b.handle(req("initialize",{"protocolVersion":"2025-11-25"}))["result"]["protocolVersion"],"2025-11-25")
        b.handle({"jsonrpc":"2.0","method":"notifications/initialized"})
        self.assertEqual([t["name"] for t in b.handle(req("tools/list"))["result"]["tools"]],["position-sizing"])
        result=b.handle(req("tools/call",{"name":"position-sizing","arguments":{"values":[10000]}}))["result"]
        self.assertFalse(result["isError"])
        self.assertIn("20",result["content"][0]["text"])
        self.assertTrue(b.handle(req("tools/call",{"name":"black-scholes","arguments":{"values":[]}}))["result"]["isError"])
    def test_cancel_targets_only_exact_active_job(self):
        signal=threading.Event()
        with patch.dict(gateway.ACTIVE_JOBS,{"a"*32:signal},clear=True):
            self.assertFalse(gateway.cancel_job("b"*32)["accepted"])
            self.assertFalse(signal.is_set())
            self.assertTrue(gateway.cancel_job("a"*32)["accepted"])
            self.assertTrue(signal.is_set())
if __name__=="__main__":unittest.main()
