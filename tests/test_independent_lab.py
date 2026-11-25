import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lab", ROOT / "lab" / "manager.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class LabTests(unittest.TestCase):
    def test_manifest(self):
        pins = lab.load_manifest(ROOT / "lab" / "repositories.json")
        self.assertEqual(len(pins), 24)

    def test_path_and_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                lab.source(root, "../bad", "a" * 40)
            with self.assertRaises(ValueError):
                lab.source(root, "owner/repo", "HEAD")
            self.assertEqual(lab.classify("skills/demo/SKILL.md", "100644"), "skill")
            self.assertEqual(lab.classify("scripts/test.py", "100644"), "program")
            self.assertEqual(lab.classify("hooks/run.sh", "100755"), "hook")
            self.assertEqual(lab.classify("package.json", "100644"), "manifest")
            self.assertEqual(lab.classify("vendor", "160000"), "submodule")

    def test_inventory_real_git_and_dirty_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            subprocess.run(["git", "init", "-q", str(path)], check=True)
            (path / "test.py").write_text("print('fixture')\n")
            subprocess.run(["git", "-C", str(path), "add", "."], check=True)
            subprocess.run(["git", "-C", str(path), "-c", "user.name=Lab", "-c",
                            "user.email=lab@example.invalid", "commit", "-qm", "fixture"], check=True)
            commit = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"]).decode().strip()
            self.assertEqual(lab.inventory(path, commit)["counts"], {"program": 1})
            (path / "extra").write_text("fixture")
            with self.assertRaises(ValueError):
                lab.verify(path, commit)

    def test_exact_approval_and_isolation(self):
        p = {"repo": "owner/repo", "commit": "a" * 40, "image": "sha256:" + "b" * 64,
             "timeout": 60, "steps": [["python3", "test.py", "a; echo unsafe"]]}
        original = lab.digest(p)
        with patch.object(lab, "verify") as verify:
            with self.assertRaises(ValueError):
                lab.run_plan(Path("/tmp"), p, "wrong")
            verify.assert_not_called()
        args = lab.docker_args(Path("/tmp/source"), p, "lab-test")
        for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "--user=65534:65534", "--pull=never"]:
            self.assertIn(flag, args)
        self.assertIn("'a; echo unsafe'", args[-1])
        p["timeout"] = 61
        self.assertNotEqual(lab.digest(p), original)

if __name__ == "__main__":
    unittest.main()
