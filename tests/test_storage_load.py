"""Tests for P0-B2: idempotent price loading and pipeline run records."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import run_data_pipeline
from src.storage import get_conn, init_db, load_prices, record_run


class StorageLoadTests(unittest.TestCase):
    """Every test runs against an isolated temporary SQLite database."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self._temporary.name)
        self.db_path = self.folder / "nested" / "test_load.db"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    @staticmethod
    def _frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-01", "2026-07-02"],
                "name": ["黄瓜", "西红柿", "黄瓜"],
                "price": [3.0, 4.5, 3.25],
                "source": ["fixture", "fixture", "fixture"],
            }
        )

    def _scalar(self, sql: str, params: tuple = ()) -> object:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def test_load_prices_is_idempotent_for_row_counts(self) -> None:
        first = load_prices(self._frame(), db_path=self.db_path)
        second = load_prices(self._frame(), db_path=self.db_path)

        self.assertEqual(first["rows_in"], 3)
        self.assertEqual(first["prices_upserted"], 3)
        self.assertEqual(second["prices_upserted"], 3)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM fact_price"), 3)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dim_date"), 2)

    def test_changed_price_updates_existing_fact_row(self) -> None:
        load_prices(self._frame(), db_path=self.db_path)

        changed = self._frame()
        changed.loc[
            (changed["date"] == "2026-07-01") & (changed["name"] == "黄瓜"),
            "price",
        ] = 9.75
        load_prices(changed, db_path=self.db_path)

        self.assertEqual(self._scalar("SELECT COUNT(*) FROM fact_price"), 3)
        price = self._scalar(
            "SELECT f.price FROM fact_price f "
            "JOIN dim_commodity c ON c.commodity_id = f.commodity_id "
            "WHERE f.date_id = ? AND c.name = ?",
            ("2026-07-01", "黄瓜"),
        )
        self.assertAlmostEqual(float(price), 9.75)

    def test_commodities_are_not_duplicated_across_loads(self) -> None:
        load_prices(self._frame(), db_path=self.db_path)
        load_prices(self._frame(), db_path=self.db_path)

        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dim_commodity"), 2)
        duplicates = self._scalar(
            "SELECT COUNT(*) FROM ("
            "SELECT name FROM dim_commodity GROUP BY name HAVING COUNT(*) > 1"
            ")"
        )
        self.assertEqual(duplicates, 0)

    def test_watermark_tracks_max_loaded_date(self) -> None:
        load_prices(self._frame(), db_path=self.db_path)

        self.assertEqual(
            self._scalar(
                "SELECT last_date_id FROM etl_watermark WHERE pipeline = ?",
                ("price_pipeline",),
            ),
            "2026-07-02",
        )

    def test_record_run_inserts_and_updates_same_run_id(self) -> None:
        record_run(
            "run-1",
            "price_pipeline",
            "running",
            rows_in=3,
            db_path=self.db_path,
        )
        record_run(
            "run-1",
            "price_pipeline",
            "success",
            rows_in=3,
            rows_out=3,
            db_path=self.db_path,
        )

        self.assertEqual(self._scalar("SELECT COUNT(*) FROM pipeline_run"), 1)
        self.assertEqual(
            self._scalar("SELECT status FROM pipeline_run WHERE run_id = 'run-1'"),
            "success",
        )
        self.assertEqual(
            self._scalar("SELECT rows_out FROM pipeline_run WHERE run_id = 'run-1'"),
            3,
        )

    def test_failed_load_rolls_back_the_whole_batch(self) -> None:
        invalid = pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-02"],
                "name": ["黄瓜", "西红柿"],
                "price": [3.0, 0.0],
                "source": ["fixture", "fixture"],
            }
        )
        with self.assertRaises(sqlite3.IntegrityError):
            load_prices(invalid, db_path=self.db_path)

        self.assertEqual(self._scalar("SELECT COUNT(*) FROM fact_price"), 0)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dim_date"), 0)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dim_commodity"), 0)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM etl_watermark"), 0)

    def test_pipeline_with_load_db_end_to_end(self) -> None:
        artifacts = run_data_pipeline(
            prefer_network=False,
            raw_path=self.folder / "raw.csv",
            processed_path=self.folder / "processed.csv",
            metadata_path=self.folder / "metadata.json",
            load_db=True,
            db_path=self.db_path,
        )

        self.assertGreater(len(artifacts.data), 0)
        self.assertEqual(
            self._scalar("SELECT COUNT(*) FROM fact_price"),
            len(artifacts.data),
        )
        self.assertEqual(
            self._scalar(
                "SELECT status FROM pipeline_run ORDER BY started_at DESC LIMIT 1"
            ),
            "success",
        )
        self.assertEqual(
            self._scalar(
                "SELECT last_date_id FROM etl_watermark WHERE pipeline = ?",
                ("price_pipeline",),
            ),
            artifacts.data["date"].max().strftime("%Y-%m-%d"),
        )

    def test_pipeline_without_load_db_does_not_create_database(self) -> None:
        run_data_pipeline(
            prefer_network=False,
            raw_path=self.folder / "raw.csv",
            processed_path=self.folder / "processed.csv",
            metadata_path=self.folder / "metadata.json",
            db_path=self.db_path,
        )

        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
