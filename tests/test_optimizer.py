"""Batch 5 tests for the V2.0 planting combination optimizer."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.optimizer import optimize_planting


class PlantingOptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plants = pd.DataFrame(
            [
                {
                    "name": "攻击A",
                    "sun_cost": 50,
                    "score": 10,
                    "attack": 8,
                    "defense": 2,
                    "control": 0,
                    "role": "远程输出",
                    "category": "攻击",
                },
                {
                    "name": "防御B",
                    "sun_cost": 25,
                    "score": 4,
                    "attack": 0,
                    "defense": 9,
                    "control": 0,
                    "role": "前排防御",
                    "category": "防御",
                },
                {
                    "name": "控制C",
                    "sun_cost": 25,
                    "score": 6,
                    "attack": 0,
                    "defense": 2,
                    "control": 8,
                    "role": "减速控制",
                    "category": "辅助",
                },
                {
                    "name": "免费攻击D",
                    "sun_cost": 0,
                    "score": 3,
                    "attack": 3,
                    "defense": 1,
                    "control": 0,
                    "role": "低费输出",
                    "category": "攻击",
                },
            ]
        )

    def assert_valid_result(self, result: dict, sun: int, cells: int) -> None:
        self.assertTrue(result["all_constraints_met"])
        self.assertTrue(all(result["constraint_checks"].values()))
        self.assertLessEqual(result["total_sun_cost"], sun)
        self.assertLessEqual(result["total_plants"], cells)
        self.assertGreater(result["total_score"], 0)
        self.assertTrue(result["recommendation_reason"])

    def test_pulp_solution_respects_all_constraints(self) -> None:
        result = optimize_planting(
            self.plants, available_sun=75, available_cells=4
        )
        self.assertEqual(result["method"], "pulp")
        self.assert_valid_result(result, 75, 4)

    def test_greedy_fallback_respects_all_constraints(self) -> None:
        result = optimize_planting(
            self.plants,
            available_sun=75,
            available_cells=4,
            use_pulp=False,
        )
        self.assertEqual(result["method"], "greedy")
        self.assert_valid_result(result, 75, 4)

    def test_zero_cost_plant_cannot_exceed_cell_limit(self) -> None:
        result = optimize_planting(
            self.plants, available_sun=25, available_cells=3
        )
        self.assertLessEqual(result["total_plants"], 3)
        self.assertTrue(result["constraint_checks"]["cell_limit"])

    def test_infeasible_resources_return_empty_combination(self) -> None:
        result = optimize_planting(
            self.plants, available_sun=0, available_cells=1
        )
        self.assertFalse(result["all_constraints_met"])
        self.assertEqual(result["strategy"], {})
        self.assertIn("Infeasible", result["status"])

    def test_total_score_matches_combination_subtotals(self) -> None:
        result = optimize_planting(
            self.plants, available_sun=75, available_cells=4
        )
        expected = sum(item["subtotal_score"] for item in result["combination"])
        self.assertAlmostEqual(result["total_score"], expected)


if __name__ == "__main__":
    unittest.main()
