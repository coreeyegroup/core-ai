#!/usr/bin/env python3
"""Independent repository lab. No application, database or model dependency."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
SHA = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
REPO = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*")
PROGRAMS = {".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".ps1", ".bat", ".rb", ".go", ".rs", ".php", ".java", ".c", ".cpp"}
MANIFESTS = {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "pyproject.toml", "uv.lock", "poetry.lock", "pipfile", "pipfile.lock", "dockerfile", "compose.yaml", "compose.yml", "docker-compose.yml", "makefile", "cargo.toml", "cargo.lock", "go.mod", "go.sum", "plugin.json", "hooks.json", "mcp.json", ".mcp.json", "marketplace.json"}

def valid(repo, commit):
    if not isinstance(repo, str) or not REPO.fullmatch(repo):
        raise ValueError("Expected owner/repository")
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError("Expected a full lowercase commit SHA")

def safe_path(root, *parts):
    p = root.resolve()
    for part in parts:
        if part in {"", ".", ".."} or "/" in part or "\\" in part:
            raise ValueError("Invalid managed path")
        p = p / part
        if p.is_symlink():
            raise ValueError("Refusing symlink in managed path")
    return p

def source(root, repo, commit):
    valid(repo, commit)
    return safe_path(root, "repositories", *repo.split("/"), commit)

def git(path, *args):
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL") if k in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never",
         "-c", "protocol.ext.allow=never", "-C", str(path), *args],
        env=env, timeout=600)

def checkout(root, repo, commit):
    path = source(root, repo, commit)
    if path.exists():
        verify(path, commit)
        return path
    path.mkdir(parents=True, exist_ok=False)
    git(path, "init", "--quiet")
    git(path, "fetch", "--quiet", "--depth=1", "--no-tags", "--no-recurse-submodules",
        f"https://github.com/{repo}.git", commit)
    if git(path, "rev-parse", "FETCH_HEAD").decode().strip() != commit:
        raise ValueError("Fetched commit does not match approved pin")
    git(path, "checkout", "--quiet", "--detach", commit)
    verify(path, commit)
    return path

def verify(path, commit):
    if not (path / ".git").is_dir() or (path / ".git").is_symlink():
        raise ValueError("Managed checkout is missing or invalid")
    if git(path, "rev-parse", "--show-toplevel").decode().strip() != str(path.resolve()):
        raise ValueError("Unexpected repository root")
    if git(path, "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("Checkout is not at the pinned commit")
    if git(path, "status", "--porcelain", "--untracked-files=all", "--ignored"):
        raise ValueError("Checkout contains local changes or extra files; preserve it and review manually")

def classify(path, mode):
    p = PurePosixPath(path)
    name = p.name.lower()
    if mode == "160000":
        return "submodule"
    if mode == "120000":
        return "symlink"
    if name == "skill.md":
        return "skill"
    if name.endswith(".agent.md") or ("agents" in p.parts[:-1] and p.suffix == ".md"):
        return "agent-candidate"
    if name.startswith(("license", "licence", "copying", "notice")):
        return "license"
    if "hooks" in p.parts[:-1]:
        return "hook"
    if name in MANIFESTS or name.startswith(("requirements", "dockerfile.")):
        return "manifest"
    if p.suffix.lower() in PROGRAMS or mode == "100755":
        return "program"
    if p.suffix.lower() in {".md", ".rst", ".txt"}:
        return "documentation"
    return "other"

def inventory(path, commit):
    verify(path, commit)
    entries = []
    for record in git(path, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not record:
            continue
        meta, raw = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = raw.decode("utf-8", errors="surrogateescape")
        entries.append({"path": name, "mode": mode, "object": oid,
                        "kind": classify(name, mode)})
    return {"commit": commit, "file_count": len(entries),
            "counts": dict(collections.Counter(e["kind"] for e in entries)),
            "files": entries}

def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")

def report(root, repo, data):
    valid(repo, data["commit"])
    p = safe_path(root, "reports", *repo.split("/"), data["commit"], uuid.uuid4().hex + ".json")
    write_new(p, data)
    return p

def load_manifest(path):
    d = json.loads(path.read_text())
    if d.get("schema") != 1 or not isinstance(d.get("repositories"), dict):
        raise ValueError("Invalid manifest")
    for repo, commit in d["repositories"].items():
        valid(repo, commit)
    return d["repositories"]

def validate_plan(p):
    if not isinstance(p, dict) or set(p) != {"repo", "commit", "image", "steps", "timeout"}:
        raise ValueError("Plan must contain repo, commit, image, steps, timeout")
    valid(p["repo"], p["commit"])
    if not isinstance(p["image"], str) or not IMAGE.fullmatch(p["image"]):
        raise ValueError("Use the exact locally inspected Docker image ID (sha256:...)")
    if type(p["timeout"]) is not int or not 1 <= p["timeout"] <= 600:
        raise ValueError("Timeout must be 1–600 seconds")
    if not isinstance(p["steps"], list) or not 1 <= len(p["steps"]) <= 12:
        raise ValueError("Plan must contain 1–12 command argv lists")
    for step in p["steps"]:
        if not isinstance(step, list) or not 1 <= len(step) <= 32 or any(
            not isinstance(x, str) or not x or len(x) > 2000 or "\x00" in x for x in step
        ):
            raise ValueError("Invalid command argv")
    return p

def digest(p):
    return hashlib.sha256(json.dumps(validate_plan(p), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def docker_args(path, plan, name):
    # Source is read-only, all writes are ephemeral; no host credentials, socket or network.
    command = "set -eu; mkdir -p /tmp/home /tmp/work; cp -R /source/. /tmp/work/; cd /tmp/work; "
    command += "; ".join(shlex.join(step) for step in plan["steps"])
    return ["docker", "run", "--rm", "--name", name, "--pull=never", "--network=none",
            "--read-only", "--user=65534:65534", "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true", "--pids-limit=128",
            "--memory=1g", "--memory-swap=1g", "--cpus=1",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m,mode=1777",
            "--mount", f"type=bind,src={path},dst=/source,readonly",
            "--env", "HOME=/tmp/home", "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint", "/bin/sh", plan["image"], "-c", command]

def run_plan(root, plan, approved):
    if approved != digest(plan):
        raise ValueError("Approval does not match exact plan digest")
    path = source(root, plan["repo"], plan["commit"])
    verify(path, plan["commit"])
    name = "core-ai-lab-" + uuid.uuid4().hex
    state = {"repo": plan["repo"], "commit": plan["commit"], "plan_digest": approved,
             "image": plan["image"], "state": "failed", "exit_code": None}
    try:
        # Output is streamed to the operator, not persisted automatically.
        result = subprocess.run(docker_args(path, plan, name), timeout=plan["timeout"], check=False)
        state.update(exit_code=result.returncode, state="passed-exit" if result.returncode == 0 else "failed")
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], timeout=20, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state["state"] = "timeout"
    finally:
        print("Execution record:", report(root, plan["repo"], state))
    return 0 if state["state"] == "passed-exit" else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "core-ai-lab")
    parser.add_argument("--manifest", type=Path, default=HERE / "repositories.json")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    for action in ("sync", "inventory"):
        q = sub.add_parser(action)
        q.add_argument("repo", help="owner/repository or all")
        q.add_argument("--commit", help="Override pin for one repository only")
    q = sub.add_parser("review-plan")
    q.add_argument("plan", type=Path)
    q = sub.add_parser("run-plan")
    q.add_argument("plan", type=Path)
    q.add_argument("--approve", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action in {"review-plan", "run-plan"}:
        plan = validate_plan(json.loads(args.plan.read_text()))
        if args.action == "review-plan":
            print(json.dumps(plan, indent=2))
            print("Approval digest:", digest(plan))
            return 0
        return run_plan(root, plan, args.approve)
    pins = load_manifest(args.manifest)
    if args.action == "list":
        for repo, commit in pins.items():
            print(repo, commit, "present" if source(root, repo, commit).exists() else "not-downloaded")
        return 0
    if args.repo == "all" and args.commit:
        raise ValueError("A commit override requires one repository")
    if args.repo != "all":
        commit = args.commit or pins.get(args.repo)
        valid(args.repo, commit)
        pins = {args.repo: commit}
    failed = False
    for repo, commit in pins.items():
        try:
            path = source(root, repo, commit)
            if args.action == "sync":
                path = checkout(root, repo, commit)
            data = inventory(path, commit)
            print(repo, commit, data["counts"], "report:", report(root, repo, data))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            failed = True
            print(repo, "FAILED:", str(exc), file=sys.stderr)
    return int(failed)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("STOP:", str(exc), file=sys.stderr)
        sys.exit(1)
