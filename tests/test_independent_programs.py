import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
try:
    programs = importlib.import_module("programs")
finally:
    sys.path.pop(0)

IMAGE = "sha256:" + "a" * 64
NAME = "ui-ux-pro-max"

class ProgramRecipeTests(unittest.TestCase):
    def test_plan_pin_and_arguments(self):
        p = programs.plan(NAME, IMAGE, "-query; echo", "-project", smoke=True)
        self.assertEqual(p["commit"], "8db36338810d0942567b97ce439affd1619fcf31")
        self.assertEqual(p["steps"][0][-3:], ["--project-name=-project", "--", "-query; echo"])
        self.assertIn("design_system", p["steps"][0][2])
        self.assertEqual(p["commit"], programs.manager.load_manifest(
            Path(programs.__file__).parent / "repositories.json")[p["repo"]])

    def test_approval_and_failed_install(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(programs.manager, "run_plan", return_value=1) as runner:
            root = Path(temp)
            with self.assertRaises(ValueError):
                programs.install(root, NAME, IMAGE, "invalid")
            runner.assert_not_called()
            approved = programs.manager.digest(programs.plan(NAME, IMAGE, smoke=True))
            self.assertEqual(programs.install(root, NAME, IMAGE, approved), 1)
            self.assertFalse(programs.receipt_path(root, NAME, IMAGE).exists())

    def test_receipt_and_independent_run(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(programs.manager, "run_plan", return_value=0) as runner:
            root = Path(temp)
            with self.assertRaises(ValueError):
                programs.run(root, NAME, IMAGE, "test query", "Example")
            approved = programs.manager.digest(programs.plan(NAME, IMAGE, smoke=True))
            self.assertEqual(programs.install(root, NAME, IMAGE, approved), 0)
            self.assertTrue(programs.receipt_path(root, NAME, IMAGE).is_file())
            self.assertEqual(programs.install(root, NAME, IMAGE, approved), 0)
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(programs.run(root, NAME, IMAGE, "test query", "Example"), 0)
            self.assertEqual(runner.call_args.args[1]["steps"][0][-1], "test query")
            with self.assertRaises(ValueError):
                programs.run(root, NAME, "sha256:" + "b" * 64, "test query", "Example")

    def test_smoke_schema_accepts_and_rejects(self):
        import subprocess
        valid = '{"design_system":{"colors":{"a":1},"typography":{"a":1},"style":{"a":1},"pattern":{"a":1}}}'
        for payload, expected in [(valid, 0), ('{"design_system":{}}', 1)]:
            proc = subprocess.run([sys.executable, "-c", programs.CHECK, sys.executable, "-c",
                                   "print(" + repr(payload) + ")"], capture_output=True)
            self.assertEqual(proc.returncode, expected)

if __name__ == "__main__":
    unittest.main()
