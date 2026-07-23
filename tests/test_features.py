"""Dedicated tests for deterministic price feature engineering."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.features import FEATURE_COLUMNS, add_price_features
from src.preprocess import STANDARD_COLUMNS


class PriceFeatureTests(unittest.TestCase):
    def _prices(
        self,
        prices: list[float],
        *,
        names: list[str] | None = None,
    ) -> pd.DataFrame:
        row_count = len(prices)
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-07-01", periods=row_count),
                "name": names or ["黄瓜"] * row_count,
                "price": prices,
                "source": ["fixture"] * row_count,
            }
        )

    def test_single_row_produces_valid_features(self) -> None:
        featured = add_price_features(self._prices([5.0]))

        self.assertEqual(len(featured), 1)
        self.assertTrue(
            all(
                math.isfinite(float(featured.iloc[0][column]))
                for column in FEATURE_COLUMNS
            )
        )
        self.assertEqual(featured.iloc[0]["price_ma7"], 5.0)
        self.assertEqual(featured.iloc[0]["volatility"], 0.0)

    def test_constant_prices_produce_zero_volatility(self) -> None:
        featured = add_price_features(self._prices([3.5, 3.5, 3.5]))

        self.assertTrue(featured["volatility"].abs().lt(1e-12).all())

    def test_all_columns_present(self) -> None:
        featured = add_price_features(self._prices([2.0, 4.0]))

        self.assertTrue(set(FEATURE_COLUMNS).issubset(featured.columns))

    def test_inf_values_replaced_with_zero(self) -> None:
        featured = add_price_features(self._prices([0.0, 1.0]))

        self.assertFalse(
            any(
                math.isinf(float(value))
                for value in featured[list(FEATURE_COLUMNS)].to_numpy().flat
            )
        )
        self.assertEqual(featured.iloc[-1]["change_rate"], 0.0)

    def test_price_unit_attr_preserved(self) -> None:
        prices = self._prices([2.0])
        prices.attrs["price_unit"] = "fixture-unit"

        featured = add_price_features(prices)

        self.assertEqual(featured.attrs["price_unit"], "fixture-unit")

    def test_empty_input_handled(self) -> None:
        empty = pd.DataFrame(columns=list(STANDARD_COLUMNS))

        featured = add_price_features(empty)

        self.assertTrue(featured.empty)
        self.assertEqual(
            featured.columns.tolist(),
            [*STANDARD_COLUMNS, *FEATURE_COLUMNS],
        )

    def test_grouped_calculation(self) -> None:
        prices = pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-01", "2026-07-02", "2026-07-02"],
                "name": ["黄瓜", "白菜", "黄瓜", "白菜"],
                "price": [2.0, 10.0, 4.0, 10.0],
                "source": ["fixture"] * 4,
            }
        )

        featured = add_price_features(prices)
        cucumber = featured.loc[featured["name"] == "黄瓜"].iloc[-1]
        cabbage = featured.loc[featured["name"] == "白菜"].iloc[-1]

        self.assertAlmostEqual(cucumber["price_ma7"], 3.0)
        self.assertAlmostEqual(cucumber["volatility"], 1.0 / 3.0)
        self.assertAlmostEqual(cabbage["price_ma7"], 10.0)
        self.assertAlmostEqual(cabbage["volatility"], 0.0)


if __name__ == "__main__":
    unittest.main()
