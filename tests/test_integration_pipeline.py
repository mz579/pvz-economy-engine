"""P0 acceptance test: build -> load -> DQ -> query on a temporary database."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_db_path
from src.pipeline import run_data_pipeline
from src.storage import init_db, recent_avg_price


class PipelineIntegrationTests(unittest.TestCase):
    """The whole P0 chain runs against a temp directory, never ``data/pvz.db``."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self._temporary.name)
        self.db_path = self.folder / "data" / "acceptance.db"
        self.repository_db = get_db_path()
        self._repository_snapshot = self._snapshot(self.repository_db)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    @staticmethod
    def _snapshot(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns)

    def _scalar(self, sql: str, params: tuple = ()) -> object:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def _run_pipeline(self) -> None:
        init_db(self.db_path)
        run_data_pipeline(
            prefer_network=False,
            raw_path=self.folder / "raw" / "latest_prices.csv",
            processed_path=self.folder / "processed" / "vegetable_prices.csv",
            metadata_path=self.folder / "raw" / "metadata.json",
            load_db=True,
            db_path=self.db_path,
        )

    def test_pipeline_loads_prices_run_record_and_dq_results(self) -> None:
        self._run_pipeline()

        self.assertGreater(self._scalar("SELECT COUNT(*) FROM fact_price"), 0)
        self.assertGreater(
            self._scalar(
                "SELECT COUNT(*) FROM pipeline_run WHERE status = 'success'"
            ),
            0,
        )
        self.assertGreater(self._scalar("SELECT COUNT(*) FROM dq_result"), 0)

    def test_recent_avg_price_returns_a_non_empty_window(self) -> None:
        self._run_pipeline()

        result = recent_avg_price("土豆", db_path=self.db_path)

        self.assertEqual(result["name"], "土豆")
        self.assertGreater(result["days"], 0)
        self.assertIsNotNone(result["avg_price"])
        self.assertGreater(result["avg_price"], 0)
        self.assertLessEqual(result["days"], 7)
        self.assertEqual(
            result["as_of"],
            self._scalar(
                "SELECT MAX(f.date_id) FROM fact_price AS f "
                "JOIN dim_commodity AS c ON c.commodity_id = f.commodity_id "
                "WHERE c.name = '土豆'"
            ),
        )

    def test_recent_avg_price_honours_window_and_as_of(self) -> None:
        self._run_pipeline()

        full = recent_avg_price("土豆", days=7, db_path=self.db_path)
        short = recent_avg_price(
            "土豆", days=3, as_of=full["as_of"], db_path=self.db_path
        )
        missing = recent_avg_price("不存在的品类", db_path=self.db_path)

        self.assertEqual(short["days"], 3)
        self.assertEqual(short["as_of"], full["as_of"])
        self.assertEqual(missing["days"], 0)
        self.assertIsNone(missing["avg_price"])

    def test_repository_database_is_not_touched(self) -> None:
        self.assertNotEqual(self.db_path.resolve(), self.repository_db.resolve())

        self._run_pipeline()

        self.assertEqual(
            self._snapshot(self.repository_db), self._repository_snapshot
        )


if __name__ == "__main__":
    unittest.main()
