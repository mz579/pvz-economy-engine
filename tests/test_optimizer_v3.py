"""Tests for the V3 step-1 sun economy + combat optimizer."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard import load_offline_prices
from src.optimizer_v3 import MUSHROOMS, optimize_planting_v3
from src.plant_mapping import load_plant_mapping
from src.scoring import calculate_apocalypse_scores


class OptimizerV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plants = load_plant_mapping()
        cls.ranking = calculate_apocalypse_scores(
            cls.plants,
            load_offline_prices(),
        )
        cls.indexed = cls.plants.set_index("name")

    def selected_names(self, result: dict) -> set[str]:
        return {
            name for name, quantity in result["strategy"].items() if quantity > 0
        }

    def test_real_150_sun_20_cells_respects_all_constraints(self) -> None:
        result = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
            scenario="night",
        )

        self.assertTrue(result["all_constraints_met"])
        self.assertTrue(all(result["constraint_checks"].values()))
        self.assertTrue(result["v3_constraint_checks"]["has_production"])
        self.assertLessEqual(result["total_sun_cost"], 150)
        self.assertLessEqual(result["total_plants"], 20)
        self.assertEqual(result["total_plants"], 20)
        self.assertEqual(result["unused_cells"], 0)
        self.assertEqual(result["unused_cells_reason"], "")
        self.assertEqual(result["method"], "v3-simulation")
        self.assertEqual(result["score_column"], "apocalypse_index")

        selected = self.selected_names(result)
        producers = set(self.indexed.index[self.indexed["production"] > 0])
        attackers = set(self.indexed.index[self.indexed["category"] == "攻击"])
        supporters = set(
            self.indexed.index[
                self.indexed["category"].eq("防御")
                | self.indexed["role"].str.contains("防御|控制", regex=True)
                | self.indexed["defense"].ge(5)
                | self.indexed["control"].ge(5)
            ]
        )

        self.assertTrue(selected & producers, "组合必须包含至少 1 个产能植物")
        self.assertTrue(selected & attackers, "组合必须包含至少 1 个攻击植物")
        self.assertTrue(selected & supporters, "组合必须包含至少 1 个防御/控制植物")
        self.assertIn("阳光菇", selected)

        # 0 阳光植物不受付费植物的集中度上限约束。
        self.assertGreater(result["strategy"]["小喷菇"], result["per_plant_limit"])
        for item in result["combination"]:
            bound = (
                20
                if float(item["unit_sun_cost"]) == 0
                else result["per_plant_limit"]
            )
            with self.subTest(plant=item["name"]):
                self.assertLessEqual(int(item["quantity"]), bound)

    def test_sun_economy_and_combat_fields_are_complete(self) -> None:
        result = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
            scenario="night",
        )
        economy = result["sun_economy"]
        combat = result["combat"]

        self.assertEqual(
            set(economy),
            {
                "start_sun",
                "initial_cost",
                "production_over_horizon",
                "sky_sun_per_sec",
                "sky_sun_over_horizon",
                "ending_sun",
                "payback_seconds",
                "horizon",
            },
        )
        self.assertEqual(economy["start_sun"], 150)
        self.assertEqual(economy["initial_cost"], result["total_sun_cost"])
        self.assertEqual(economy["horizon"], 120)
        self.assertGreater(economy["production_over_horizon"], 0)
        self.assertGreaterEqual(economy["ending_sun"], 0)
        self.assertEqual(economy["sky_sun_per_sec"], 0.0)
        self.assertEqual(economy["sky_sun_over_horizon"], 0.0)
        self.assertEqual(
            economy["ending_sun"],
            round(
                economy["start_sun"]
                - economy["initial_cost"]
                + economy["production_over_horizon"],
                4,
            ),
        )
        self.assertAlmostEqual(economy["payback_seconds"]["阳光菇"], 30.0, places=2)

        self.assertEqual(
            set(combat),
            {"total_dps", "total_wall_hp", "effective_defense", "horizon"},
        )
        self.assertGreaterEqual(combat["total_dps"], 0)
        self.assertGreater(combat["total_dps"], 0)
        self.assertGreater(combat["total_wall_hp"], 0)
        self.assertGreaterEqual(combat["effective_defense"], combat["total_wall_hp"])
        self.assertEqual(combat["horizon"], 120)

    def test_lane_deployment_keeps_selection_and_covers_five_lanes(self) -> None:
        result = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
            scenario="night",
        )
        lane_defense = result["lane_defense"]

        self.assertEqual(lane_defense["lanes_count"], 5)
        self.assertEqual(len(lane_defense["lanes"]), 5)
        self.assertEqual(
            sum(lane["capacity"] for lane in lane_defense["lanes"]),
            20,
        )
        self.assertEqual(
            sum(
                sum(lane["plants"].values())
                for lane in lane_defense["lanes"]
            ),
            result["total_plants"],
        )
        self.assertIn(lane_defense["weakest_lane"], range(1, 6))
        self.assertTrue(result["v3_constraint_checks"]["has_attack_per_lane"])
        self.assertIn("5 车道部署", result["recommendation_reason"])
        # The lane layer must not perturb the step-1 selection.
        self.assertDictEqual(
            result["strategy"],
            {"阳光菇": 1, "土豆雷": 4, "灯笼草": 1, "小喷菇": 14},
        )
        for lane in lane_defense["lanes"]:
            with self.subTest(lane=lane["lane"]):
                self.assertGreater(lane["dps"], 0)
                self.assertLessEqual(lane["cells"], lane["capacity"])
                self.assertEqual(
                    lane["cells"],
                    sum(lane["plants"].values()),
                )
        weakest = next(
            lane
            for lane in lane_defense["lanes"]
            if lane["lane"] == lane_defense["weakest_lane"]
        )
        self.assertEqual(
            lane_defense["weakest_survivability"],
            weakest["survivability"],
        )

    def test_optimizer_is_deterministic(self) -> None:
        first = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
        )
        second = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
        )
        self.assertEqual(first, second)

    def test_night_scenario_keeps_mushrooms_and_no_sky_sun(self) -> None:
        result = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
            scenario="night",
        )

        self.assertEqual(result["scenario"], "night")
        self.assertTrue(result["all_constraints_met"])
        selected = self.selected_names(result)
        self.assertTrue(selected & MUSHROOMS, "夜间应允许蘑菇入选")
        self.assertIn("小喷菇", selected)
        # The free mushroom attacker can fill more than the paid-plant cap.
        self.assertGreater(result["strategy"]["小喷菇"], result["per_plant_limit"])
        self.assertGreater(result["strategy"]["小喷菇"], 6)
        self.assertEqual(result["total_plants"], 20)

        economy = result["sun_economy"]
        self.assertEqual(economy["sky_sun_per_sec"], 0.0)
        self.assertEqual(economy["sky_sun_over_horizon"], 0.0)
        self.assertEqual(
            economy["ending_sun"],
            round(
                economy["start_sun"]
                - economy["initial_cost"]
                + economy["production_over_horizon"],
                4,
            ),
        )
        self.assertIn("夜间", result["recommendation_reason"])
        self.assertIn("蘑菇可用", result["recommendation_reason"])

    def test_day_scenario_excludes_mushrooms_and_adds_sky_sun(self) -> None:
        result = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
            scenario="day",
        )

        self.assertEqual(result["scenario"], "day")
        self.assertTrue(result["all_constraints_met"])
        selected = self.selected_names(result)
        self.assertFalse(selected & MUSHROOMS, "白天蘑菇休眠，不应入选")
        for mushroom in ("小喷菇", "阳光菇", "大喷菇"):
            self.assertNotIn(mushroom, result["strategy"])

        economy = result["sun_economy"]
        self.assertEqual(economy["sky_sun_per_sec"], 0.25)
        self.assertEqual(economy["sky_sun_over_horizon"], 30.0)
        self.assertEqual(
            economy["ending_sun"],
            round(
                economy["start_sun"]
                - economy["initial_cost"]
                + economy["production_over_horizon"]
                + economy["sky_sun_over_horizon"],
                4,
            ),
        )
        self.assertIn("白天", result["recommendation_reason"])
        self.assertIn("蘑菇", result["recommendation_reason"])
        self.assertIn("天降阳光", result["recommendation_reason"])

    def test_explicit_sky_sun_overrides_scenario_default(self) -> None:
        result = optimize_planting_v3(
            self.ranking,
            available_sun=150,
            available_cells=20,
            scenario="day",
            sky_sun_per_sec=0.0,
        )
        self.assertEqual(result["sun_economy"]["sky_sun_per_sec"], 0.0)
        self.assertEqual(result["sun_economy"]["sky_sun_over_horizon"], 0.0)

    def test_invalid_scenario_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "day 或 night"):
            optimize_planting_v3(
                self.ranking,
                available_sun=150,
                available_cells=20,
                scenario="dusk",
            )

    def test_infeasible_pool_returns_empty_constraint_checked_result(self) -> None:
        attack_only = pd.DataFrame(
            [
                {
                    "name": "豌豆射手",
                    "sun_cost": 100,
                    "attack": 20,
                    "defense": 3,
                    "production": 0,
                    "control": 0,
                    "special_tag": "SINGLE",
                    "role": "远程输出",
                    "category": "攻击",
                    "hp": 100,
                    "apocalypse_index": 0.1,
                }
            ]
        )
        result = optimize_planting_v3(
            attack_only,
            available_sun=150,
            available_cells=20,
        )
        self.assertFalse(result["all_constraints_met"])
        self.assertEqual(result["strategy"], {})
        self.assertFalse(result["combination"])
        self.assertIn("防御/控制植物", result["recommendation_reason"])
        self.assertEqual(result["lane_defense"]["lanes"], [])
        self.assertEqual(result["lane_defense"]["lanes_count"], 5)
        self.assertIsNone(result["lane_defense"]["weakest_lane"])
        self.assertEqual(result["lane_defense"]["weakest_survivability"], 0)
        self.assertFalse(result["v3_constraint_checks"]["has_attack_per_lane"])


if __name__ == "__main__":
    unittest.main()
