import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
try:
    trading = importlib.import_module("trading_programs")
finally:
    sys.path.pop(0)

IMAGE = "sha256:" + "d" * 64

class TradingRecipeTests(unittest.TestCase):
    def test_plans_pin_and_compile(self):
        pins = trading.manager.load_manifest(Path(trading.__file__).parent / "repositories.json")
        for name, item in trading.RECIPES.items():
            p = trading.plan(name, IMAGE)
            self.assertEqual(p["commit"], pins[p["repo"]])
            self.assertEqual(p["steps"][0][3], item["entry"])
            compile(p["steps"][0][2], "<fixture>", "exec")
            self.assertIn("--network=none", trading.manager.docker_args(Path("/tmp/source"), p, "test"))

    def test_black_scholes_documented_approximation_bound(self):
        from collections import namedtuple
        from contextlib import redirect_stdout
        import io
        import runpy

        Price = namedtuple("Price", "call put")
        Greeks = namedtuple("Greeks", "delta gamma")
        step = trading.plan("black-scholes", IMAGE)["steps"][0]
        self.assertLessEqual(len(step[2]), 2000)

        def check_fixture(call, put, call_delta=0.63683065):
            upstream = {
                "price_option": lambda *a: Price(call, put),
                "compute_greeks": lambda *a: Greeks(
                    call_delta if a[-1] == "call" else -0.36316935,
                    0.018762017345846895),
            }
            with patch.object(runpy, "run_path", return_value=upstream), patch.object(sys, "argv", step[2:]), redirect_stdout(io.StringIO()):
                exec(compile(step[2], "<qualification>", "exec"), {})

        # Reproduce the observed result and the corresponding pinned algorithm's put.
        check_fixture(10.450575619322287, 5.5735180693936925)
        check_fixture(10.450583572185565, 5.573526022256971)
        # Common-mode price errors must fail even when put-call parity is intact.
        with self.assertRaises(SystemExit):
            check_fixture(10.450583572185565 + 0.00002, 5.573526022256971 + 0.00002)
        # A parity error within both individual price bounds must still fail.
        with self.assertRaises(SystemExit):
            check_fixture(10.450583572185565 + 0.000005, 5.573526022256971 - 0.000005)
        # Greek invariants retain their original tolerance.
        with self.assertRaises(SystemExit):
            check_fixture(10.450575619322287, 5.5735180693936925, 0.64)

    def test_bad_inputs(self):
        for name, args in [("position-sizing", [100, .01, 5, 5, 0, 0]),
                           ("kelly-criterion", [1.2, 2]),
                           ("kelly-criterion", [float("nan"), 2]),
                           ("black-scholes", [100, 100, 0, .05, .2]),
                           ("bond-pricing", [1000, .05, .05, 20.5, 2])]:
            with self.assertRaises(ValueError):
                trading.plan(name, IMAGE, args)

    def test_qualification_and_run(self):
        name = "position-sizing"
        with tempfile.TemporaryDirectory() as tmp, patch.object(trading.manager, "run_plan") as runner:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                trading.install(root, name, IMAGE, "wrong")
            runner.assert_not_called()
            with self.assertRaises(ValueError):
                trading.run(root, name, IMAGE, [10000, .01, 100, 95, 0, 0])
            digest = trading.manager.digest(trading.plan(name, IMAGE))
            runner.return_value = 1
            self.assertEqual(trading.install(root, name, IMAGE, digest), 1)
            self.assertFalse(trading.receipt(root, name, IMAGE)[0].exists())
            runner.return_value = 0
            self.assertEqual(trading.install(root, name, IMAGE, digest), 0)
            self.assertEqual(trading.run(root, name, IMAGE, [20000, .01, 100, 95, 0, 0]), 0)

if __name__ == "__main__":
    unittest.main()
