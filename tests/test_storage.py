"""Tests for the P0-B1 SQLite storage layer."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage import get_conn, init_db


EXPECTED_TABLES = {
    "dim_date",
    "dim_commodity",
    "fact_price",
    "strategy_result",
    "pipeline_run",
    "etl_watermark",
}


class StorageTests(unittest.TestCase):
    """Each test uses an isolated temporary database."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        # The nested directory also verifies get_conn creates parents.
        self.db_path = Path(self._temporary.name) / "nested" / "test_pvz.db"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _tables(self) -> set[str]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        finally:
            conn.close()
        return {row[0] for row in rows}

    def test_init_db_creates_expected_tables(self) -> None:
        created = init_db(self.db_path)

        self.assertEqual(created, self.db_path.resolve())
        self.assertTrue(self.db_path.is_file())
        self.assertEqual(self._tables(), EXPECTED_TABLES)

    def test_price_check_constraint_rejects_non_positive_price(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fact_price (date_id, commodity_id, price) "
                    "VALUES ('2024-01-01', 1, -1)"
                )
        finally:
            conn.close()

    def test_unique_date_commodity_rejects_duplicates(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                "INSERT INTO fact_price (date_id, commodity_id, price) "
                "VALUES ('2024-01-01', 1, 2.5)"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fact_price (date_id, commodity_id, price) "
                    "VALUES ('2024-01-01', 1, 3.0)"
                )
        finally:
            conn.close()

    def test_strategy_result_primary_key_is_run_and_date(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            pk_columns = [
                row[1]
                for row in conn.execute("PRAGMA table_info(strategy_result)")
                if row[5] > 0
            ]
        finally:
            conn.close()

        self.assertEqual(pk_columns, ["run_id", "date_id"])

    def test_strategy_result_rejects_duplicate_run_date(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                "INSERT INTO strategy_result (run_id, date_id, planting, score) "
                "VALUES ('run-1', '2024-01-01', 'sunflower', 1.0)"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO strategy_result (run_id, date_id, planting, score) "
                    "VALUES ('run-1', '2024-01-01', 'peashooter', 2.0)"
                )
        finally:
            conn.close()

    def test_strategy_result_rejects_null_run_id(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO strategy_result (run_id, date_id, planting, score) "
                    "VALUES (NULL, '2024-01-01', 'sunflower', 1.0)"
                )
        finally:
            conn.close()

    def test_strategy_result_rejects_null_date_id(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO strategy_result (run_id, date_id, planting, score) "
                    "VALUES ('run-1', NULL, 'sunflower', 1.0)"
                )
        finally:
            conn.close()

    def test_dim_date_rejects_null_date_id(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO dim_date (date_id) VALUES (NULL)")
        finally:
            conn.close()

    def test_get_conn_usable_and_enables_foreign_keys(self) -> None:
        init_db(self.db_path)
        conn = get_conn(self.db_path)
        try:
            self.assertEqual(conn.execute("SELECT 1").fetchone(), (1,))
            self.assertEqual(
                conn.execute("PRAGMA foreign_keys").fetchone(), (1,)
            )
        finally:
            conn.close()

    def test_init_db_is_idempotent(self) -> None:
        init_db(self.db_path)
        init_db(self.db_path)

        self.assertEqual(self._tables(), EXPECTED_TABLES)


if __name__ == "__main__":
    unittest.main()
