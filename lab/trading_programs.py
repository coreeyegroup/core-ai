#!/usr/bin/env python3
"""Pinned offline financial calculators. No broker access or order execution."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import manager

REPO = "agiprolabs/claude-trading-skills"
COMMIT = "981e1d736cdc02bdc1c55c74ec9224e956414706"
# Each entry calls the upstream implementation, not a replacement formula.
RECIPES = {
    "position-sizing": {
        "entry": "skills/position-sizing/scripts/size_calculator.py",
        "fields": ["account", "risk_pct", "entry", "stop", "fee_rate", "slippage"],
        "fixture": [10000, 0.01, 100, 95, 0, 0],
        "body": "result = m['fixed_fractional'](*a)",
        "check": "close(result['units'], 20); close(result['risk_amount'], 100); close(result['effective_risk'], 5)",
    },
    "kelly-criterion": {
        "entry": "skills/kelly-criterion/scripts/kelly_calculator.py",
        "fields": ["win_rate", "payoff_ratio"],
        "fixture": [0.6, 2],
        "body": "result = {'full_kelly': m['kelly_fraction'](*a), 'edge': m['edge'](*a)}",
        "check": "close(result['full_kelly'], 0.4); close(result['edge'], 0.8)",
    },
    "black-scholes": {
        "entry": "skills/options-pricing/scripts/black_scholes.py",
        "fields": ["spot", "strike", "years", "annual_rate", "annual_volatility"],
        "fixture": [100, 100, 1, 0.05, 0.2],
        "body": """prices = m['price_option'](*a)
result = {'prices': prices._asdict(), 'call_greeks': m['compute_greeks'](*a, 'call')._asdict(), 'put_greeks': m['compute_greeks'](*a, 'put')._asdict()}""",
        "check": """S, K, T, r, sigma = a
discount = math.exp(-r*T)
# Upstream CDF approximation has documented maximum absolute error 7.5e-8.
# Propagate both weighted CDF errors; allow 1e-9 for reference rounding.
price_bound = 7.5e-8 * (S + K*discount) + 1e-9
for kind, reference in [('call', 10.450583572), ('put', 5.573526022)]:
    actual = result['prices'][kind]
    if not math.isfinite(actual) or abs(actual-reference) > price_bound:
        raise SystemExit('Option premium outside CDF error bound: %s %r (bound %r)' % (kind, actual, price_bound))
close(result['prices']['call'] - result['prices']['put'], S-K*discount)
close(result['call_greeks']['delta'] - result['put_greeks']['delta'], 1)
close(result['call_greeks']['gamma'], result['put_greeks']['gamma'])""",
    },
    "bond-pricing": {
        "entry": "skills/fixed-income/scripts/bond_calculator.py",
        "fields": ["face", "annual_coupon", "annual_ytm", "periods", "frequency"],
        "fixture": [1000, 0.05, 0.05, 20, 2],
        "body": "result = m['analyze_bond'](*a)._asdict()",
        "check": "close(result['dirty_price'], 1000); close(result['current_yield'], 0.05)",
    },
}

PREFIX = """import json, math, runpy, sys
m = runpy.run_path(sys.argv[1])
a = json.loads(sys.argv[2])
def close(actual, expected):
    if not math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-7):
        raise SystemExit('Unexpected fixture result: %r != %r' % (actual, expected))
"""
SUFFIX = "\nprint(json.dumps(result, indent=2, allow_nan=False))\n"

def parameters(name, values):
    recipe = RECIPES[name]
    if not isinstance(values, list) or len(values) != len(recipe["fields"]):
        raise ValueError("Expected JSON array: " + ", ".join(recipe["fields"]))
    if any(type(v) not in (int, float) or abs(v) > 1e12 or not math.isfinite(v) for v in values):
        raise ValueError("Use finite numeric inputs within +/- 1e12")
    a = values
    if name == "position-sizing":
        account, risk, entry, stop, fee, slip = a
        valid = account > 0 and 0 < risk <= 1 and entry > 0 and stop > 0 and entry != stop and 0 <= fee <= 1 and 0 <= slip <= 1
    elif name == "kelly-criterion":
        valid = 0 <= a[0] <= 1 and a[1] > 0
    elif name == "black-scholes":
        valid = a[0] > 0 and a[1] > 0 and 0 < a[2] <= 100 and -1 <= a[3] <= 1 and 0 < a[4] <= 10
    else:
        valid = (a[0] > 0 and 0 <= a[1] <= 1 and -1 < a[2] <= 1
                 and type(a[3]) is int and 1 <= a[3] <= 1200
                 and type(a[4]) is int and a[4] in (1, 2, 4, 12))
    if not valid:
        raise ValueError("Invalid or unsupported calculation inputs")
    return a

def plan(name, image, values=None):
    recipe = RECIPES[name]
    smoke = values is None
    a = parameters(name, recipe["fixture"] if smoke else values)
    script = PREFIX + recipe["body"] + "\n" + (recipe["check"] + "\n" if smoke else "") + SUFFIX
    return manager.validate_plan({"repo": REPO, "commit": COMMIT, "image": image,
        "steps": [["python3", "-c", script, recipe["entry"], json.dumps(a, allow_nan=False)]], "timeout": 120})

def receipt(root, name, image):
    p = plan(name, image)
    return (manager.safe_path(root, "packages", name, COMMIT, image[7:] + ".json"),
            {"recipe": name, "repo": REPO, "commit": COMMIT, "image": image,
             "qualification_digest": manager.digest(p), "status": "qualified-numeric-fixture"})

def install(root, name, image, approved):
    p = plan(name, image)
    if approved != manager.digest(p):
        raise ValueError("Approval does not match exact reviewed plan")
    dest, data = receipt(root, name, image)
    if dest.exists():
        if json.loads(dest.read_text()) != data:
            raise ValueError("Existing receipt differs; preserve and review")
        print("Already qualified:", dest)
        return 0
    rc = manager.run_plan(root, p, approved)
    if rc == 0:
        manager.write_new(dest, data)
        print("Independent program qualified:", dest)
    return rc

def run(root, name, image, values):
    p = plan(name, image, values)
    dest, data = receipt(root, name, image)
    if not dest.is_file() or json.loads(dest.read_text()) != data:
        raise ValueError("Qualify this recipe and exact runtime first")
    print("Model calculation only; not a trading instruction or executable broker quantity.", file=sys.stderr)
    return manager.run_plan(root, p, manager.digest(p))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "core-ai-lab")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    for action in ("review", "install", "run"):
        q = sub.add_parser(action)
        q.add_argument("recipe", choices=RECIPES)
        q.add_argument("--image", required=True)
        if action == "install":
            q.add_argument("--approve", required=True)
        if action == "run":
            q.add_argument("--params", required=True, help="JSON array in listed field order")
    a = parser.parse_args()
    if a.action == "list":
        for name, item in RECIPES.items():
            print(name, json.dumps(item["fields"]), "fixture:", json.dumps(item["fixture"]))
        return 0
    if a.action == "review":
        p = plan(a.recipe, a.image)
        print(json.dumps(p, indent=2))
        print("Approval digest:", manager.digest(p))
        return 0
    if a.action == "install":
        return install(a.root, a.recipe, a.image, a.approve)
    return run(a.root, a.recipe, a.image, json.loads(a.params))

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("STOP:", str(exc), file=sys.stderr)
        sys.exit(1)
