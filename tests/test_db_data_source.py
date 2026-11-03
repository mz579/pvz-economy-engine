"""Tests for the SQLite dashboard data source and its CSV fallback."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard import build_dashboard_model
from src.storage import init_db, load_prices
from src.storage.price_source import load_price_features_from_db


PROCESSED_CSV = ROOT / "data" / "processed" / "vegetable_prices.csv"
EXPECTED_COLUMNS = [
    "date",
    "name",
    "price",
    "source",
    "historical_mean",
    "volatility",
]


class DbPriceSourceTests(unittest.TestCase):
    """Each test loads the real processed sample into an isolated database."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self._temporary.name)
        self.db_path = self.folder / "prices.db"
        init_db(self.db_path)
        self.processed = pd.read_csv(PROCESSED_CSV, parse_dates=["date"])
        load_prices(self.processed, db_path=self.db_path)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_features_have_one_row_per_commodity(self) -> None:
        frame = load_price_features_from_db(self.db_path)

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(list(frame.columns), EXPECTED_COLUMNS)
        self.assertEqual(len(frame), 15)
        self.assertEqual(frame["name"].nunique(), 15)
        self.assertTrue((frame["price"] > 0).all())
        self.assertTrue(frame["historical_mean"].notna().all())
        self.assertTrue((frame["historical_mean"] > 0).all())
        self.assertTrue((frame["volatility"] >= 0).all())
        self.assertEqual(frame.attrs["price_unit"], "元/kg")
        self.assertIn("data_days_old", frame.attrs)

    def test_features_match_processed_latest_row_per_commodity(self) -> None:
        frame = load_price_features_from_db(self.db_path).set_index("name")
        latest = (
            self.processed.sort_values("date")
            .groupby("name", as_index=True)
            .tail(1)
            .set_index("name")
        )

        self.assertEqual(
            frame["date"].max(),
            self.processed["date"].max(),
        )
        for name, expected in latest.iterrows():
            with self.subTest(name=name):
                self.assertAlmostEqual(
                    float(frame.loc[name, "price"]),
                    float(expected["price"]),
                )
                self.assertAlmostEqual(
                    float(frame.loc[name, "historical_mean"]),
                    float(expected["historical_mean"]),
                    places=6,
                )
                self.assertAlmostEqual(
                    float(frame.loc[name, "volatility"]),
                    float(expected["volatility"]),
                    places=6,
                )

    def test_missing_or_empty_database_returns_none(self) -> None:
        self.assertIsNone(
            load_price_features_from_db(self.folder / "missing.db")
        )
        empty_db = self.folder / "empty.db"
        init_db(empty_db)
        self.assertIsNone(load_price_features_from_db(empty_db))

    def test_dashboard_model_uses_db_backend(self) -> None:
        model = build_dashboard_model(
            "均衡巡逻",
            150,
            20,
            data_backend="db",
            db_path=self.db_path,
        )

        self.assertEqual(model["data_backend_used"], "db")
        self.assertEqual(model["data_mode"], "SQLite 数据库")
        self.assertIn("SQLite 数据库", model["data_source"])
        self.assertEqual(len(model["ranking"]), 15)
        self.assertTrue(model["result"]["all_constraints_met"])
        self.assertTrue(model["result"]["strategy"])

    def test_dashboard_model_falls_back_to_csv_when_db_missing(self) -> None:
        model = build_dashboard_model(
            "均衡巡逻",
            150,
            20,
            data_backend="db",
            db_path=self.folder / "absent.db",
        )

        self.assertEqual(model["data_backend_used"], "csv")
        self.assertNotEqual(model["data_mode"], "SQLite 数据库")
        self.assertFalse(model["prices"].empty)
        self.assertTrue(model["result"]["all_constraints_met"])

    def test_default_backend_stays_csv(self) -> None:
        model = build_dashboard_model("均衡巡逻", 150, 20)

        self.assertEqual(model["data_backend_used"], "csv")


if __name__ == "__main__":
    unittest.main()
