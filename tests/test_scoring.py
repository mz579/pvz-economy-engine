"""Batch 4 tests for the explainable apocalypse scoring model."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import load_or_build_processed_prices
from src.plant_mapping import load_plant_mapping
from src.scoring import DEFAULT_WEIGHTS, calculate_apocalypse_scores


class ApocalypseScoringTests(unittest.TestCase):
    def _single_plant(self, sun_cost: int = 100) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "name": "测试植物",
                    "vegetable_name": "测试菜",
                    "sun_cost": sun_cost,
                    "attack": 100,
                    "defense": 8,
                    "production": 6,
                    "control": 4,
                    "special_ability": "测试范围能力",
                    "role": "测试定位",
                    "special_tag": "AOE",
                }
            ]
        )

    def _single_price(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2026-07-13",
                    "name": "测试菜",
                    "price": 2.0,
                    "source": "fixture",
                    "historical_mean": 4.0,
                    "volatility": 0.25,
                }
            ]
        )

    def test_formula_matches_all_visible_components(self) -> None:
        scored = calculate_apocalypse_scores(self._single_plant(), self._single_price())
        row = scored.iloc[0]
        expected_battle = 10 * 0.35 + 8 * 0.25 + 6 * 0.20 + 4 * 0.15 + 10 * 0.05
        expected_index = expected_battle * 2.0 * 0.8 / 100
        self.assertAlmostEqual(row["battle_value"], expected_battle)
        self.assertAlmostEqual(row["price_undervaluation"], 2.0)
        self.assertAlmostEqual(row["stability_coefficient"], 0.8)
        self.assertAlmostEqual(row["apocalypse_index"], expected_index)
        self.assertTrue(row["recommendation_reason"])

    def test_zero_sun_uses_protective_denominator(self) -> None:
        scored = calculate_apocalypse_scores(
            self._single_plant(sun_cost=0), self._single_price()
        )
        self.assertEqual(scored.iloc[0]["effective_sun_cost"], 25)
        self.assertIn("保护值", scored.iloc[0]["recommendation_reason"])

    def test_all_zero_attack_raises_value_error(self) -> None:
        plants = pd.DataFrame(
            [
                {
                    "name": "无攻击植物",
                    "vegetable_name": "测试菜",
                    "sun_cost": 100,
                    "attack": 0,
                    "defense": 5,
                    "production": 0,
                    "control": 0,
                    "special_ability": "测试",
                    "role": "测试",
                }
            ]
        )
        with self.assertRaises(ValueError) as context:
            calculate_apocalypse_scores(plants, self._single_price())
        self.assertIn("攻击", str(context.exception))

    def test_bundled_mapping_produces_complete_ranking(self) -> None:
        plants = load_plant_mapping()
        prices = load_or_build_processed_prices()
        scored = calculate_apocalypse_scores(plants, prices)
        self.assertEqual(len(scored), len(plants))
        self.assertEqual(scored["rank"].tolist(), list(range(1, len(plants) + 1)))
        self.assertTrue(scored["recommendation_reason"].str.len().gt(0).all())
        self.assertEqual(set(DEFAULT_WEIGHTS), set(scored.attrs["weights"]))

    def test_component_contributions_rebuild_battle_value(self) -> None:
        scored = calculate_apocalypse_scores(
            load_plant_mapping(), load_or_build_processed_prices()
        )
        contribution_columns = [
            f"{dimension}_contribution" for dimension in DEFAULT_WEIGHTS
        ]
        rebuilt = scored[contribution_columns].sum(axis=1)
        self.assertTrue((rebuilt.sub(scored["battle_value"]).abs() < 1e-12).all())


if __name__ == "__main__":
    unittest.main()
