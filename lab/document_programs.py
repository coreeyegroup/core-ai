#!/usr/bin/env python3
"""Run pinned upstream document utilities independently of CORE-AI."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

import manager

REPO = "anthropics/skills"
COMMIT = "e4bb5d960d87126ff3b3a8af1a104b7db67560ba"
PDF_SMOKE = """from pathlib import Path
import subprocess, sys
def fixture(path, form):
    objs = [b'<< /Type /Catalog /Pages 2 0 R' + (b' /AcroForm << /Fields [4 0 R] >>' if form else b'') + b' >>',
            b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300]' + (b' /Annots [4 0 R]' if form else b'') + b' >>']
    if form:
        objs.append(b'<< /Type /Annot /Subtype /Widget /FT /Tx /T (CoreEye) /V (test) /Rect [10 10 100 30] /P 3 0 R >>')
    data = b'%PDF-1.4\\n'
    offsets = [0]
    for i, obj in enumerate(objs, 1):
        offsets.append(len(data))
        data += str(i).encode() + b' 0 obj\\n' + obj + b'\\nendobj\\n'
    pos = len(data)
    data += ('xref\\n0 %d\\n0000000000 65535 f \\n' % len(offsets)).encode()
    for offset in offsets[1:]:
        data += ('%010d 00000 n \\n' % offset).encode()
    data += ('trailer\\n<< /Size %d /Root 1 0 R >>\\nstartxref\\n%d\\n%%%%EOF\\n' % (len(offsets), pos)).encode()
    Path(path).write_bytes(data)
for form in (False, True):
    path = '/tmp/form.pdf' if form else '/tmp/plain.pdf'
    fixture(path, form)
    out = subprocess.check_output([sys.executable, sys.argv[1], path], text=True)
    expected = 'This PDF has fillable form fields' if form else 'This PDF does not have fillable form fields'
    if not out.strip().startswith(expected):
        raise SystemExit('Unexpected PDF form detection')
    print(out.strip())
"""
PPTX_SMOKE = """from pptx import Presentation
from pptx.util import Inches
import subprocess, sys
deck = Presentation()
for marker in ('CoreEye qualification alpha', 'CoreEye qualification beta'):
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text = marker
deck.save('/tmp/fixture.pptx')
out = subprocess.check_output([sys.executable, sys.argv[1], '/tmp/fixture.pptx'], text=True)
for marker in ('<!-- Slide number: 1 -->', '<!-- Slide number: 2 -->', 'CoreEye qualification alpha', 'CoreEye qualification beta'):
    if marker not in out:
        raise SystemExit('Missing slide extraction marker: ' + marker)
print(out)
"""
RECIPES = {
    "pdf-form-check": ("skills/pdf/scripts/check_fillable_fields.py", {".pdf"}, PDF_SMOKE),
    "pptx-text": ("skills/pptx/scripts/slide_text.py", {".pptx", ".pptm", ".potx", ".ppsx"}, PPTX_SMOKE),
}

def plan(name, image):
    entry, _, smoke = RECIPES[name]
    return manager.validate_plan({"repo": REPO, "commit": COMMIT, "image": image,
                                  "steps": [["python3", "-c", smoke, entry]], "timeout": 120})

def receipt(root, name, image):
    p = plan(name, image)
    return (manager.safe_path(root, "packages", name, COMMIT, image[7:] + ".json"),
            {"recipe": name, "repo": REPO, "commit": COMMIT, "image": image,
             "qualification_digest": manager.digest(p), "status": "qualified-fixture"})

def install(root, name, image, approved):
    p = plan(name, image)
    if manager.digest(p) != approved:
        raise ValueError("Approval does not match reviewed fixture plan")
    dest, data = receipt(root, name, image)
    if dest.exists():
        if json.loads(dest.read_text()) != data:
            raise ValueError("Receipt differs; preserve and review")
        print("Already qualified:", dest)
        return 0
    rc = manager.run_plan(root, p, approved)
    if rc == 0:
        manager.write_new(dest, data)
        print("Independent program qualified:", dest)
    return rc

def input_file(path, name):
    path = path.resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in RECIPES[name][1]:
        raise ValueError("Expected an existing document of the supported type")
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Initial input limit is 32 MiB")
    if any(c in str(path) for c in (",", "\n", "\r", '"')):
        raise ValueError("Use a path without Docker mount delimiters")
    return path

def command(root, name, image, path, container):
    path = input_file(path, name)
    checkout = manager.source(root, REPO, COMMIT)
    target = "/input" + path.suffix.lower()
    p = manager.validate_plan({"repo": REPO, "commit": COMMIT, "image": image,
         "steps": [["python3", RECIPES[name][0], target]], "timeout": 120})
    args = manager.docker_args(checkout, p, container)
    index = args.index("--entrypoint")
    args[index:index] = ["--mount", f"type=bind,src={path},dst={target},readonly"]
    return p, args

def run(root, name, image, path):
    dest, data = receipt(root, name, image)
    if not dest.is_file() or json.loads(dest.read_text()) != data:
        raise ValueError("Qualify this recipe and exact runtime image first")
    manager.verify(manager.source(root, REPO, COMMIT), COMMIT)
    container = "core-ai-lab-doc-" + uuid.uuid4().hex
    p, args = command(root, name, image, path, container)
    state = {"repo": REPO, "commit": COMMIT, "recipe": name, "image": image,
             "state": "failed", "exit_code": None}
    try:
        result = subprocess.run(args, timeout=p["timeout"], check=False)
        state.update(exit_code=result.returncode,
                     state="passed-exit" if result.returncode == 0 else "failed")
    except subprocess.TimeoutExpired:
        state["state"] = "timeout"
        subprocess.run(["docker", "kill", container], timeout=20, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        print("Execution record:", manager.report(root, REPO, state), file=sys.stderr)
    return int(state["state"] != "passed-exit")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "core-ai-lab")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    for action in ("review", "install", "run"):
        p = sub.add_parser(action)
        p.add_argument("recipe", choices=RECIPES)
        p.add_argument("--image", required=True)
        if action == "install":
            p.add_argument("--approve", required=True)
        if action == "run":
            p.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "list":
        for name, (entry, extensions, _) in RECIPES.items():
            print(name, entry, ", ".join(sorted(extensions)))
        return 0
    if args.action == "review":
        p = plan(args.recipe, args.image)
        print(json.dumps(p, indent=2))
        print("Approval digest:", manager.digest(p))
        return 0
    if args.action == "install":
        return install(args.root, args.recipe, args.image, args.approve)
    return run(args.root, args.recipe, args.image, args.input)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("STOP:", str(exc), file=sys.stderr)
        sys.exit(1)
