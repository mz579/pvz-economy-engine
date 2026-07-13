"""Batch 1 smoke tests for the V2.0 project boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ProjectStructureTests(unittest.TestCase):
    def test_v2_structure_exists(self) -> None:
        expected = [
            "app.py",
            "AGENTS.md",
            "LEGACY.md",
            "assets/style.css",
            "assets/plant_icons/README.md",
            "data/raw/README.md",
            "data/processed/README.md",
        ]
        for relative_path in expected:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_root_app_is_valid_python(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        ast.parse(source)

    def test_heavy_v3_dependencies_are_excluded(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        for package in ("airflow", "prophet", "xgboost", "scipy"):
            with self.subTest(package=package):
                self.assertNotIn(package, requirements)

    def test_package_version_marks_v2_development(self) -> None:
        from src import __version__

        self.assertTrue(__version__.startswith("2.0.0"))


class CompatibilitySmokeTests(unittest.TestCase):
    def test_existing_offline_pipeline_still_returns_a_strategy(self) -> None:
        from src.optimizer import run_optimization
        from src.valuator import calc_deviation, calculate_utility

        plants = pd.read_csv(ROOT / "data" / "plants.csv")
        prices = pd.read_csv(ROOT / "data" / "fallback" / "vegetable_prices.csv")
        prices["date"] = pd.to_datetime(prices["date"])

        utility = calculate_utility(plants)
        deviation = calc_deviation(prices, utility)
        merged = plants.merge(utility[["name", "utility"]], on="name")
        result = run_optimization(
            merged,
            deviation,
            available_sun=150,
            available_cells=20,
        )

        self.assertIn("strategy", result)
        self.assertIn("status", result)
        self.assertLessEqual(result["total_cost"], 150)
        self.assertLessEqual(result["total_plants"], 20)


if __name__ == "__main__":
    unittest.main()
