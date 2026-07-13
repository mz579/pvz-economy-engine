"""Acceptance tests for the downloadable local release package."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_release import build_release


class ReleasePackageTests(unittest.TestCase):
    def test_portable_zip_contains_runtime_and_region_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = build_release("v2.0.0-test", Path(temporary))
            self.assertTrue(archive.is_file())
            with ZipFile(archive) as package:
                names = set(package.namelist())

        prefix = "pvz-economy-engine-v2.0.0-test/"
        expected = {
            f"{prefix}app.py",
            f"{prefix}README_FIRST.txt",
            f"{prefix}requirements.txt",
            f"{prefix}start_windows.bat",
            f"{prefix}start_unix.sh",
            f"{prefix}src/scoring.py",
            f"{prefix}src/user_data.py",
            f"{prefix}data/fallback/vegetable_prices.csv",
            f"{prefix}data/templates/regional_prices_template.csv",
            f"{prefix}docs/screenshots/dashboard.png",
        }
        self.assertTrue(expected.issubset(names))
        self.assertFalse(any("backtester" in name or "airflow" in name for name in names))


if __name__ == "__main__":
    unittest.main()
