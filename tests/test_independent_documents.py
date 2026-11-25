import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
try:
    docs = importlib.import_module("document_programs")
finally:
    sys.path.pop(0)

IMAGE = "sha256:" + "b" * 64

class DocumentRecipeTests(unittest.TestCase):
    def test_plans(self):
        for name in docs.RECIPES:
            p = docs.plan(name, IMAGE)
            self.assertEqual(p["commit"], docs.COMMIT)
            self.assertEqual(p["repo"], docs.REPO)
            compile(p["steps"][0][2], "<fixture>", "exec")
            self.assertEqual(p["commit"], docs.manager.load_manifest(
                Path(docs.__file__).parent / "repositories.json")[p["repo"]])

    def test_approval_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(docs.manager, "run_plan") as runner:
            root = Path(tmp)
            name = "pdf-form-check"
            with self.assertRaises(ValueError):
                docs.install(root, name, IMAGE, "wrong")
            runner.assert_not_called()
            digest = docs.manager.digest(docs.plan(name, IMAGE))
            runner.return_value = 1
            self.assertEqual(docs.install(root, name, IMAGE, digest), 1)
            dest, _ = docs.receipt(root, name, IMAGE)
            self.assertFalse(dest.exists())
            runner.return_value = 0
            self.assertEqual(docs.install(root, name, IMAGE, digest), 0)
            self.assertTrue(dest.exists())

    def test_document_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "example.pdf"
            path.write_bytes(b"fixture")
            p, args = docs.command(root, "pdf-form-check", IMAGE, path, "doc-test")
            self.assertIn("type=bind,src=" + str(path) + ",dst=/input.pdf,readonly", args)
            self.assertIn("--network=none", args)
            self.assertIn("--read-only", args)
            self.assertEqual(p["steps"][0][-1], "/input.pdf")
            with self.assertRaises(ValueError):
                docs.command(root, "pptx-text", IMAGE, path, "doc-test")

    def test_run_requires_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                docs.run(Path(tmp), "pdf-form-check", IMAGE, Path(tmp) / "missing.pdf")

if __name__ == "__main__":
    unittest.main()
