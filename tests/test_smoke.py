"""Project-boundary smoke tests for the completed V2.1.0 workflow."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ProjectStructureTests(unittest.TestCase):
    def test_v2_structure_exists(self) -> None:
        expected = [
            "app.py",
            "cli.py",
            "AGENTS.md",
            "README.md",
            "assets/style.css",
            "assets/plant_icons/README.md",
            "data/raw/README.md",
            "data/processed/README.md",
            "src/crawler.py",
            "src/preprocess.py",
            "src/features.py",
            "src/scoring.py",
            "src/optimizer.py",
            "src/dashboard.py",
        ]
        for relative_path in expected:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_entry_points_are_valid_python(self) -> None:
        for relative_path in ("app.py", "cli.py"):
            with self.subTest(path=relative_path):
                ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))

    def test_heavy_v3_dependencies_are_excluded(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        for package in ("airflow", "prophet", "xgboost", "scipy"):
            with self.subTest(package=package):
                self.assertNotIn(package, requirements)

    def test_package_version_is_final_v2(self) -> None:
        from src import __version__

        self.assertEqual(__version__, "2.1.0")


class WorkflowSmokeTests(unittest.TestCase):
    def test_offline_workflow_returns_explainable_strategy(self) -> None:
        from src.dashboard import build_dashboard_model

        model = build_dashboard_model("均衡巡逻", 150, 20)
        result = model["result"]
        self.assertEqual(result["score_column"], "apocalypse_index")
        self.assertTrue(result["all_constraints_met"])
        self.assertLessEqual(result["total_sun_cost"], 150)
        self.assertLessEqual(result["total_plants"], 20)
        self.assertEqual(len(model["reasons"]), len(result["combination"]))


if __name__ == "__main__":
    unittest.main()
