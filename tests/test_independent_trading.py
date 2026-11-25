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
