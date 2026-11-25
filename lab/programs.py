#!/usr/bin/env python3
"""Independent, pinned program recipes. Does not import the CORE-AI backend."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import manager

RECIPES = {
    "ui-ux-pro-max": {
        "repo": "nextlevelbuilder/ui-ux-pro-max-skill",
        "commit": "8db36338810d0942567b97ce439affd1619fcf31",
        "entry": ".claude/skills/ui-ux-pro-max/scripts/search.py",
        "description": "Local design-system generator; Python 3, bundled data, no external Python packages.",
    }
}
CHECK = """import json, subprocess, sys
r = subprocess.run(sys.argv[1:], check=True, stdout=subprocess.PIPE)
d = json.loads(r.stdout)
s = d.get("design_system")
if not isinstance(s, dict) or not all(isinstance(s.get(k), dict) and s[k] for k in ("colors", "typography", "style", "pattern")):
    raise SystemExit("Invalid design system: missing nonempty required sections")
print(json.dumps(d, ensure_ascii=False, indent=2))
"""

def plan(name, image, query="institutional financial trading dashboard", project="COREI-OS-MINI", smoke=False):
    recipe = RECIPES[name]
    if not query.strip() or not project.strip():
        raise ValueError("Query and project cannot be empty")
    cmd = ["python3", recipe["entry"], "--design-system", "--json",
           "--project-name=" + project, "--", query]
    if smoke:
        cmd = ["python3", "-c", CHECK, *cmd]
    return manager.validate_plan({"repo": recipe["repo"], "commit": recipe["commit"],
                                 "image": image, "steps": [cmd], "timeout": 120})

def receipt_path(root, name, image):
    recipe = RECIPES[name]
    if not manager.IMAGE.fullmatch(image):
        raise ValueError("Supply an exact local Docker image ID")
    return manager.safe_path(root, "packages", name, recipe["commit"], image[7:] + ".json")

def receipt(name, image):
    p = plan(name, image, smoke=True)
    return {"recipe": name, "repo": p["repo"], "commit": p["commit"],
            "image": image, "qualification_digest": manager.digest(p),
            "status": "qualified-output-schema"}

def install(root, name, image, approved):
    p = plan(name, image, smoke=True)
    if approved != manager.digest(p):
        raise ValueError("Review and approve this exact qualification plan")
    dest = receipt_path(root, name, image)
    expected = receipt(name, image)
    if dest.exists():
        if json.loads(dest.read_text()) != expected:
            raise ValueError("Existing receipt differs; preserve and review it")
        print("Already qualified:", dest)
        return 0
    result = manager.run_plan(root, p, approved)
    if result != 0:
        return result
    manager.write_new(dest, expected)
    print("Independent program qualified:", dest)
    return 0

def run(root, name, image, query, project):
    dest = receipt_path(root, name, image)
    if not dest.is_file() or json.loads(dest.read_text()) != receipt(name, image):
        raise ValueError("Install and qualify this recipe and image first")
    p = plan(name, image, query, project, smoke=True)
    # An explicit operator run authorizes this fixed recipe with the supplied data.
    return manager.run_plan(root, p, manager.digest(p))

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
            p.add_argument("--query", required=True)
            p.add_argument("--project", default="Design")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "list":
        for name, recipe in RECIPES.items():
            print(name, recipe["commit"], recipe["description"])
        return 0
    if args.action == "review":
        p = plan(args.recipe, args.image, smoke=True)
        print(json.dumps(p, indent=2))
        print("Approval digest:", manager.digest(p))
        return 0
    if args.action == "install":
        return install(root, args.recipe, args.image, args.approve)
    return run(root, args.recipe, args.image, args.query, args.project)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("STOP:", str(exc), file=sys.stderr)
        sys.exit(1)
