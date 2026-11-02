"""Tests for P1-1: SQL window-function metrics and Pandas cross-check.

Every test uses an isolated temporary SQLite database so ``data/pvz.db`` is
never touched.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.features import add_price_features
from src.storage import (
    compute_metrics,
    load_prices,
    max_consecutive_up_days,
)

TOLERANCE = 1e-9
PROCESSED_CSV = ROOT / "data" / "processed" / "vegetable_prices.csv"


class SqlMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self._temporary.name)
        self.db_path = self.folder / "metrics.db"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    @staticmethod
    def _prices(
        prices: list[float],
        *,
        names: list[str],
        start: str = "2026-08-01",
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range(start, periods=len(prices)),
                "name": names,
                "price": prices,
                "source": ["fixture"] * len(prices),
            }
        )

    def test_ma_matches_pandas_for_processed_csv(self) -> None:
        raw = pd.read_csv(PROCESSED_CSV, encoding="utf-8-sig")
        columns = ["date", "name", "price"]
        if "source" in raw.columns:
            columns.append("source")
        data = raw.loc[:, columns].copy()

        load_prices(data, db_path=self.db_path)

        pandas_features = add_price_features(data.copy())
        pandas_features["date_id"] = pd.to_datetime(
            pandas_features["date"]
        ).dt.strftime("%Y-%m-%d")

        sql_metrics = compute_metrics(self.db_path)

        merged = pandas_features.merge(
            sql_metrics,
            on=["name", "date_id"],
            how="inner",
            validate="one_to_one",
        )
        self.assertEqual(len(merged), len(data))

        for pandas_column, sql_column in (
            ("price_ma7", "ma7"),
            ("price_ma14", "ma14"),
            ("price_ma30", "ma30"),
        ):
            diff = (merged[pandas_column] - merged[sql_column]).abs()
            self.assertLess(
                float(diff.max()),
                TOLERANCE,
                msg=f"{pandas_column} 与 {sql_column} 最大误差 {diff.max()}",
            )

        # The SQL path keeps every fact row and orders by name, then date.
        self.assertEqual(len(sql_metrics), len(data))
        self.assertEqual(
            sql_metrics.columns.tolist(),
            [
                "date_id",
                "name",
                "commodity_id",
                "price",
                "ma7",
                "ma14",
                "ma30",
                "price_rank",
            ],
        )

    def test_max_consecutive_up_days_on_known_sequences(self) -> None:
        # 土豆: 1,2,3 (+2), then 2 (reset), then 2,3,4,5 (+3) -> 4 days.
        # 白菜: 5,4,3 (never rises) -> 0 days.
        potatoes = self._prices(
            [1.0, 2.0, 3.0, 2.0, 3.0, 4.0, 5.0],
            names=["土豆"] * 7,
        )
        cabbages = self._prices(
            [5.0, 4.0, 3.0],
            names=["白菜"] * 3,
        )
        load_prices(
            pd.concat([potatoes, cabbages], ignore_index=True),
            db_path=self.db_path,
        )

        result = max_consecutive_up_days(self.db_path)
        days = dict(zip(result["name"], result["days"]))

        self.assertEqual(days["土豆"], 4)
        self.assertEqual(days["白菜"], 0)
        self.assertEqual(
            result.columns.tolist(), ["commodity_id", "name", "days"]
        )

    def test_price_rank_is_descending_within_each_day(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2026-08-01"] * 3,
                "name": ["黄瓜", "西红柿", "白菜"],
                "price": [1.0, 5.0, 3.0],
                "source": ["fixture"] * 3,
            }
        )
        load_prices(frame, db_path=self.db_path)

        metrics = compute_metrics(self.db_path)
        self.assertEqual(len(metrics), 3)

        # RANK() ... ORDER BY price DESC: rank 1 is the most expensive.
        by_price = metrics.sort_values("price", ascending=False)
        self.assertEqual(by_price["price_rank"].tolist(), [1, 2, 3])
        self.assertEqual(by_price.iloc[0]["name"], "西红柿")
        self.assertEqual(by_price.iloc[-1]["name"], "黄瓜")

        # A larger rank means a lower price on the same day.
        self.assertTrue(
            by_price["price"].is_monotonic_decreasing
            and by_price["price_rank"].is_monotonic_increasing
        )

    def test_price_rank_is_scoped_per_day(self) -> None:
        day_one = pd.DataFrame(
            {
                "date": ["2026-08-01"] * 2,
                "name": ["黄瓜", "西红柿"],
                "price": [1.0, 5.0],
                "source": ["fixture"] * 2,
            }
        )
        day_two = pd.DataFrame(
            {
                "date": ["2026-08-02"] * 2,
                "name": ["黄瓜", "西红柿"],
                "price": [9.0, 2.0],
                "source": ["fixture"] * 2,
            }
        )
        load_prices(
            pd.concat([day_one, day_two], ignore_index=True),
            db_path=self.db_path,
        )

        metrics = compute_metrics(self.db_path)
        ranks = {
            (row.date_id, row.name): int(row.price_rank)
            for row in metrics.itertuples(index=False)
        }

        self.assertEqual(ranks[("2026-08-01", "西红柿")], 1)
        self.assertEqual(ranks[("2026-08-01", "黄瓜")], 2)
        self.assertEqual(ranks[("2026-08-02", "黄瓜")], 1)
        self.assertEqual(ranks[("2026-08-02", "西红柿")], 2)


if __name__ == "__main__":
    unittest.main()
