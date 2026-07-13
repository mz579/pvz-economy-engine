"""Batch 3 tests for the plant-to-vegetable mapping contract."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.plant_mapping import REQUIRED_COLUMNS, link_plants_to_prices, load_plant_mapping


class PlantMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapping = load_plant_mapping()
        cls.offline_prices = pd.read_csv(
            ROOT / "data" / "fallback" / "vegetable_prices.csv"
        )

    def test_mapping_has_required_schema_and_size(self) -> None:
        self.assertTrue(set(REQUIRED_COLUMNS).issubset(self.mapping.columns))
        self.assertGreaterEqual(len(self.mapping), 12)
        self.assertLessEqual(len(self.mapping), 15)
        self.assertTrue(self.mapping["name"].is_unique)

    def test_strategy_ratings_are_bounded(self) -> None:
        for column in ("defense", "production", "control"):
            with self.subTest(column=column):
                self.assertTrue(self.mapping[column].between(0, 10).all())

    def test_every_plant_links_to_offline_prices(self) -> None:
        linked = link_plants_to_prices(self.mapping, self.offline_prices)
        self.assertSetEqual(set(linked["name"]), set(self.mapping["name"]))
        self.assertTrue(linked["price"].notna().all())

    def test_mapping_accepts_v2_price_name_field(self) -> None:
        v2_prices = self.offline_prices.rename(columns={"product": "name"})
        linked = link_plants_to_prices(self.mapping, v2_prices)
        self.assertSetEqual(set(linked["name"]), set(self.mapping["name"]))

    def test_legacy_columns_remain_available(self) -> None:
        legacy_columns = {"hp", "special_tag", "category"}
        self.assertTrue(legacy_columns.issubset(self.mapping.columns))


if __name__ == "__main__":
    unittest.main()
