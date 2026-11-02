"""Tests for P0-B3: data-quality rules, CLI, and pipeline blocking."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dq import DQError, RULES, validate
from src.dq.__main__ import main as dq_main
from src.pipeline import run_data_pipeline
from src.storage import init_db, record_dq


def _base_frame(**overrides: object) -> pd.DataFrame:
    data: dict[str, object] = {
        "date": pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03"]),
        "name": ["黄瓜", "黄瓜", "黄瓜"],
        "price": [2.0, 2.1, 2.0],
        "source": ["fixture", "fixture", "fixture"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _record(result, rule: str) -> dict[str, str]:
    return next(item for item in result.records if item["rule"] == rule)


class DQRuleTests(unittest.TestCase):
    """Each rule has a passing and a failing fixture."""

    def test_good_frame_passes_all_blocking_rules(self) -> None:
        result = validate(_base_frame())

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 7)
        self.assertEqual(
            {item["rule"] for item in result.records}, set(RULES)
        )

    def test_rules_registry_covers_r1_to_r7(self) -> None:
        self.assertEqual(set(RULES), {f"R{i}" for i in range(1, 8)})
        self.assertEqual(
            {rule for rule, meta in RULES.items() if meta["severity"] == "blocking"},
            {"R1", "R2", "R3", "R5"},
        )

    def test_r1_blank_name_is_blocking(self) -> None:
        result = validate(_base_frame(name=["黄瓜", "", "黄瓜"]))

        self.assertFalse(result.passed)
        self.assertEqual(_record(result, "R1")["status"], "fail")
        self.assertTrue(any("[R1]" in error for error in result.errors))

    def test_r1_rejects_unparseable_date_and_blank_price(self) -> None:
        result = validate(
            _base_frame(
                date=["2026-07-01", "not-a-date", "2026-07-03"],
                price=[2.0, None, 2.1],
            )
        )

        self.assertFalse(result.passed)
        self.assertEqual(_record(result, "R1")["status"], "fail")

    def test_r2_duplicate_date_name_is_blocking(self) -> None:
        result = validate(
            _base_frame(date=["2026-07-01", "2026-07-01", "2026-07-02"])
        )

        self.assertFalse(result.passed)
        self.assertEqual(_record(result, "R2")["status"], "fail")

    def test_r2_distinct_commodities_on_same_day_are_allowed(self) -> None:
        result = validate(
            _base_frame(name=["黄瓜", "西红柿", "黄瓜"])
        )

        self.assertEqual(_record(result, "R2")["status"], "pass")

    def test_r3_rejects_non_positive_price(self) -> None:
        result = validate(_base_frame(price=[-1.0, 2.0, 2.1]))

        self.assertFalse(result.passed)
        self.assertEqual(_record(result, "R3")["status"], "fail")
        self.assertIn("price", _record(result, "R3")["detail"])

    def test_r3_rejects_price_above_200(self) -> None:
        result = validate(_base_frame(price=[2.0, 250.0, 2.1]))

        self.assertFalse(result.passed)
        self.assertEqual(_record(result, "R3")["status"], "fail")

    def test_r3_accepts_boundary_price_of_200(self) -> None:
        result = validate(_base_frame(price=[2.0, 200.0, 2.1]))

        self.assertEqual(_record(result, "R3")["status"], "pass")

    def test_r4_missing_day_is_a_warning_not_a_block(self) -> None:
        result = validate(
            _base_frame(date=["2026-07-01", "2026-07-03", "2026-07-04"])
        )

        self.assertTrue(result.passed)
        self.assertEqual(_record(result, "R4")["status"], "warn")
        self.assertIn("2026-07-02", _record(result, "R4")["detail"])
        self.assertTrue(any("[R4]" in warning for warning in result.warnings))

    def test_r4_continuous_series_passes(self) -> None:
        result = validate(_base_frame())

        self.assertEqual(_record(result, "R4")["status"], "pass")

    def test_r5_missing_unit_column_is_treated_as_kg(self) -> None:
        result = validate(_base_frame())

        self.assertEqual(_record(result, "R5")["status"], "pass")
        self.assertIn("视为", _record(result, "R5")["detail"])

    def test_r5_non_kg_unit_is_blocking(self) -> None:
        result = validate(_base_frame(unit=["kg", "斤", "kg"]))

        self.assertFalse(result.passed)
        self.assertEqual(_record(result, "R5")["status"], "fail")

    def test_r5_kg_units_pass(self) -> None:
        result = validate(_base_frame(unit=["kg", "元/kg", "KG"]))

        self.assertEqual(_record(result, "R5")["status"], "pass")

    def test_r6_adjacent_jump_over_50_percent_is_a_warning(self) -> None:
        result = validate(_base_frame(price=[2.0, 3.4, 3.4]))

        self.assertTrue(result.passed)
        self.assertEqual(_record(result, "R6")["status"], "warn")
        self.assertTrue(any("[R6]" in warning for warning in result.warnings))

    def test_r6_jump_across_a_date_gap_is_ignored(self) -> None:
        result = validate(
            _base_frame(
                date=["2026-07-01", "2026-07-03", "2026-07-04"],
                price=[2.0, 5.0, 5.1],
            )
        )

        self.assertEqual(_record(result, "R6")["status"], "pass")

    def test_r7_row_count_swing_is_a_warning(self) -> None:
        result = validate(_base_frame(), prev_row_count=1)

        self.assertTrue(result.passed)
        self.assertEqual(_record(result, "R7")["status"], "warn")
        self.assertTrue(any("[R7]" in warning for warning in result.warnings))

    def test_r7_without_history_is_not_triggered(self) -> None:
        result = validate(_base_frame(), prev_row_count=None)

        self.assertEqual(_record(result, "R7")["status"], "pass")
        self.assertIn("跳过", _record(result, "R7")["detail"])

    def test_r7_within_threshold_passes(self) -> None:
        result = validate(_base_frame(), prev_row_count=3)

        self.assertEqual(_record(result, "R7")["status"], "pass")

    def test_bad_frame_fails_with_r3_error(self) -> None:
        result = validate(_base_frame(price=[-1.0, 2.0, 2.1]))

        self.assertFalse(result.passed)
        self.assertTrue(any("[R3]" in error for error in result.errors))


class DQStorageTests(unittest.TestCase):
    """SQLite persistence and pipeline blocking behaviour."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self._temporary.name)
        self.db_path = self.folder / "nested" / "dq.db"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _scalar(self, sql: str, params: tuple = ()) -> object:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(sql, params).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def test_record_dq_writes_every_rule(self) -> None:
        result = validate(_base_frame())
        inserted = record_dq("run-1", result.records, db_path=self.db_path)

        self.assertEqual(inserted, 7)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dq_result"), 7)
        self.assertEqual(
            self._scalar(
                "SELECT COUNT(*) FROM dq_result WHERE run_id = 'run-1'"
            ),
            7,
        )

    def test_record_dq_keeps_fail_rows(self) -> None:
        result = validate(_base_frame(price=[-1.0, 2.0, 2.1]))
        record_dq("run-bad", result.records, db_path=self.db_path)

        self.assertEqual(
            self._scalar(
                "SELECT status FROM dq_result WHERE run_id = 'run-bad' AND rule = 'R3'"
            ),
            "fail",
        )

    def test_cli_good_csv_exits_zero_and_writes_records(self) -> None:
        csv_path = self.folder / "good.csv"
        _base_frame().to_csv(csv_path, index=False, encoding="utf-8-sig")

        output = StringIO()
        with redirect_stdout(output):
            code = dq_main(["--csv", str(csv_path), "--db", str(self.db_path)])

        self.assertEqual(code, 0)
        self.assertIn("passed=True", output.getvalue())
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dq_result"), 7)

    def test_cli_bad_csv_exits_nonzero_and_reports_r3(self) -> None:
        csv_path = self.folder / "bad.csv"
        _base_frame(price=[-1.0, 2.0, 2.1]).to_csv(
            csv_path, index=False, encoding="utf-8-sig"
        )

        output = StringIO()
        with redirect_stdout(output):
            code = dq_main(["--csv", str(csv_path), "--db", str(self.db_path)])

        self.assertNotEqual(code, 0)
        self.assertIn("[R3]", output.getvalue())
        self.assertEqual(
            self._scalar(
                "SELECT status FROM dq_result WHERE rule = 'R3'"
            ),
            "fail",
        )

    def test_pipeline_success_writes_dq_records(self) -> None:
        artifacts = run_data_pipeline(
            prefer_network=False,
            raw_path=self.folder / "raw.csv",
            processed_path=self.folder / "processed.csv",
            metadata_path=self.folder / "metadata.json",
            load_db=True,
            db_path=self.db_path,
        )

        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dq_result"), 7)
        self.assertEqual(
            self._scalar("SELECT COUNT(*) FROM dq_result WHERE status = 'fail'"),
            0,
        )
        self.assertEqual(
            self._scalar("SELECT COUNT(*) FROM fact_price"),
            len(artifacts.data),
        )

    def test_pipeline_blocks_bad_data_and_writes_no_prices(self) -> None:
        init_db(self.db_path)
        bad_result = validate(_base_frame(price=[-1.0, 2.0, 2.1]))

        with patch("src.pipeline.validate", return_value=bad_result):
            with self.assertRaises(DQError):
                run_data_pipeline(
                    prefer_network=False,
                    raw_path=self.folder / "raw.csv",
                    processed_path=self.folder / "processed.csv",
                    metadata_path=self.folder / "metadata.json",
                    load_db=True,
                    db_path=self.db_path,
                )

        self.assertEqual(self._scalar("SELECT COUNT(*) FROM fact_price"), 0)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dim_date"), 0)
        self.assertEqual(self._scalar("SELECT COUNT(*) FROM dq_result"), 7)
        self.assertEqual(
            self._scalar(
                "SELECT status FROM pipeline_run ORDER BY rowid DESC LIMIT 1"
            ),
            "failed",
        )

    def test_pipeline_without_load_db_skips_dq(self) -> None:
        with patch("src.pipeline.validate") as mocked_validate:
            run_data_pipeline(
                prefer_network=False,
                raw_path=self.folder / "raw.csv",
                processed_path=self.folder / "processed.csv",
                metadata_path=self.folder / "metadata.json",
                db_path=self.db_path,
            )

        mocked_validate.assert_not_called()
        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
