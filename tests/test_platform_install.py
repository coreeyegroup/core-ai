import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
try:batch=importlib.import_module("platform_install")
finally:sys.path.pop(0)
class PlatformBatchTests(unittest.TestCase):
    def test_approval_and_fallback(self):
        root_plan={"schema":1,"native_only":False,"profiles":[{"profile":"example","routes":[{"profile":"example","route":"discovery"},{"profile":"example","route":"directory"}]}],"packages":[{"id":"package"}]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(batch,"plan",return_value=root_plan),patch.object(batch.native_profiles,"verify",side_effect=[1,0]) as verify,patch.object(batch.package_runtime,"plan",return_value={"id":"package"}),patch.object(batch.package_runtime,"install",return_value=0) as install:
            root=Path(tmp)
            with self.assertRaises(ValueError):batch.apply(root,root_plan,"wrong")
            verify.assert_not_called();install.assert_not_called()
            self.assertEqual(batch.apply(root,root_plan,batch.native_host.digest(root_plan)),0)
            self.assertEqual(verify.call_count,2);install.assert_called_once()
            self.assertEqual(len(list((root/"reports"/"platform-batches").glob("*.json"))),1)
if __name__=="__main__":unittest.main()
