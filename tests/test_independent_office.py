import importlib
from pathlib import Path
import io
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
try:
    docs = importlib.import_module("document_programs")
finally:
    sys.path.pop(0)

IMAGE = "sha256:" + "c" * 64

class OfficeRecipeTests(unittest.TestCase):
    def test_new_plans_and_original_recipes(self):
        for name in ("docx-merge-runs", "xlsx-recalc"):
            plan = docs.plan(name, IMAGE)
            self.assertEqual(plan["repo"], docs.REPO)
            compile(plan["steps"][0][2], "<fixture>", "exec")
            self.assertLessEqual(len(plan["steps"][0][2]), 2000)
        self.assertNotIn("pdf-form-check", docs.EDIT_RECIPES)
        self.assertNotIn("pptx-text", docs.EDIT_RECIPES)
        compile(docs.EDIT, "<edit>", "exec")

    def test_output_required_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "a.docx"
            src.write_bytes(b"original")
            for output in (None, src, root / "wrong.xlsx"):
                with self.assertRaises(ValueError):
                    docs.output_path(output, "docx-merge-runs", src)
            self.assertEqual(docs.output_path(root / "new.docx", "docx-merge-runs", src), root / "new.docx")
            self.assertEqual(src.read_bytes(), b"original")

    def test_output_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "result.xlsx"
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                z.writestr("[Content_Types].xml", "fixture")
                z.writestr("xl/workbook.xml", "fixture")
            data = stream.getvalue()
            docs.publish_output(stream, dest, "xlsx-recalc")
            self.assertEqual(dest.read_bytes(), data)
            with self.assertRaises(FileExistsError):
                docs.publish_output(stream, dest, "xlsx-recalc")
            self.assertEqual(dest.read_bytes(), data)
            with self.assertRaises(ValueError):
                docs.publish_output(io.BytesIO(), root / "bad.xlsx", "xlsx-recalc")
            self.assertFalse((root / "bad.xlsx").exists())

    def test_edit_command_read_only_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "test.xlsx"
            src.write_bytes(b"fixture")
            p, args = docs.command(root, "xlsx-recalc", IMAGE, src, "fixture")
            self.assertIn("type=bind,src=" + str(src) + ",dst=/input.xlsx,readonly", args)
            self.assertIn("--network=none", args)
            self.assertEqual(p["steps"][0][-1], "/input.xlsx")
            self.assertEqual(p["steps"][0][2], docs.EDIT)

    def test_failed_qualification_no_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(docs.manager, "run_plan", return_value=1):
            root = Path(tmp)
            for name in docs.EDIT_RECIPES:
                approval = docs.manager.digest(docs.plan(name, IMAGE))
                self.assertEqual(docs.install(root, name, IMAGE, approval), 1)
                self.assertFalse(docs.receipt(root, name, IMAGE)[0].exists())

if __name__ == "__main__":
    unittest.main()
