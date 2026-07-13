"""Tests for user-supplied regional price CSV files."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.user_data import prepare_uploaded_price_data, read_price_csv_bytes


class UserPriceDataTests(unittest.TestCase):
    def test_template_is_ready_for_feature_engineering(self) -> None:
        content = (ROOT / "data" / "templates" / "regional_prices_template.csv").read_bytes()
        result = prepare_uploaded_price_data(content, region_name="成都")
        self.assertEqual(result["name"].nunique(), 3)
        self.assertTrue(result["source"].eq("user_upload:成都").all())
        self.assertIn("historical_mean", result.columns)
        self.assertIn("volatility", result.columns)

    def test_chinese_headers_and_jin_unit_are_supported(self) -> None:
        content = "日期,品种,均价,单位\n2026-07-13,土豆,2.5,元/斤\n".encode("gb18030")
        result = prepare_uploaded_price_data(content, region_name="西安")
        self.assertEqual(result.iloc[0]["price"], 5.0)
        self.assertEqual(result.iloc[0]["source"], "user_upload:西安")

    def test_empty_upload_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "空文件"):
            read_price_csv_bytes(b"")

    def test_cli_accepts_regional_csv(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "cli.py",
                "--csv",
                "data/templates/regional_prices_template.csv",
                "--region",
                "成都",
                "--sun",
                "150",
                "--cells",
                "20",
                "--top",
                "3",
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("已读取 成都 CSV", completed.stdout)
        self.assertIn("末日性价比排名", completed.stdout)


if __name__ == "__main__":
    unittest.main()
