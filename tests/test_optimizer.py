"""Batch 5 tests for the V2.0 planting combination optimizer."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.optimizer import (
    DEFAULT_MAX_PLANT_SHARE,
    calculate_per_plant_limit,
    optimize_planting,
)


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
        self.assertTrue(result["constraint_checks"]["per_plant_limit"])
        self.assertTrue(
            all(
                int(quantity) <= int(result["per_plant_limit"])
                for quantity in result["strategy"].values()
            )
        )
        self.assertEqual(result["max_plant_share"], DEFAULT_MAX_PLANT_SHARE)

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

    def test_negative_score_zero_cost_not_selected_by_greedy(self) -> None:
        plants = pd.DataFrame(
            [
                {
                    "name": "正分攻击",
                    "sun_cost": 50,
                    "score": 10,
                    "attack": 8,
                    "defense": 2,
                    "control": 0,
                    "category": "攻击",
                    "role": "输出",
                },
                {
                    "name": "正分防御",
                    "sun_cost": 25,
                    "score": 5,
                    "attack": 0,
                    "defense": 8,
                    "control": 0,
                    "category": "防御",
                    "role": "防御",
                },
                {
                    "name": "负分零费",
                    "sun_cost": 0,
                    "score": -1,
                    "attack": 1,
                    "defense": 1,
                    "control": 0,
                    "category": "攻击",
                    "role": "陷阱",
                },
            ]
        )
        result = optimize_planting(
            plants,
            available_sun=100,
            available_cells=10,
            use_pulp=False,
        )

        self.assert_valid_result(result, 100, 10)
        self.assertNotIn("负分零费", result["strategy"])

    def test_quantity_limit_uses_ceil_at_requested_lawn_sizes(self) -> None:
        expected = {1: 1, 2: 1, 3: 1, 10: 3, 20: 6}
        for cells, limit in expected.items():
            with self.subTest(cells=cells):
                self.assertEqual(calculate_per_plant_limit(cells), limit)

    def test_arbitrarily_named_zero_cost_plant_is_capped_in_both_solvers(self) -> None:
        for use_pulp in (True, False):
            with self.subTest(use_pulp=use_pulp):
                result = optimize_planting(
                    self.plants,
                    available_sun=25,
                    available_cells=10,
                    use_pulp=use_pulp,
                )
                self.assertEqual(result["per_plant_limit"], 3)
                self.assertLessEqual(result["strategy"].get("免费攻击D", 0), 3)
                self.assert_valid_result(result, 25, 10)

    def test_low_cost_plant_and_small_candidate_pool_respect_shared_cap(self) -> None:
        candidates = pd.DataFrame(
            [
                {
                    "name": "便宜攻击苗",
                    "sun_cost": 1,
                    "score": 10,
                    "attack": 8,
                    "defense": 0,
                    "control": 0,
                    "category": "攻击",
                    "role": "输出",
                },
                {
                    "name": "便宜防线苗",
                    "sun_cost": 1,
                    "score": 5,
                    "attack": 0,
                    "defense": 8,
                    "control": 0,
                    "category": "防御",
                    "role": "防御",
                },
            ]
        )
        for use_pulp in (True, False):
            with self.subTest(use_pulp=use_pulp):
                result = optimize_planting(
                    candidates,
                    available_sun=100,
                    available_cells=20,
                    use_pulp=use_pulp,
                )
                self.assert_valid_result(result, 100, 20)
                self.assertEqual(result["per_plant_limit"], 6)
                self.assertEqual(result["total_plants"], 12)
                self.assertEqual(result["unused_cells"], 8)
                self.assertIn("单植物数量上限", result["unused_cells_reason"])
                self.assertTrue(all(quantity == 6 for quantity in result["strategy"].values()))

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
