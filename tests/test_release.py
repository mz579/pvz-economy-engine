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
                windows_launcher = package.read(
                    "pvz-economy-engine-v2.0.0-test/start_windows.bat"
                )

        prefix = "pvz-economy-engine-v2.0.0-test/"
        expected = {
            f"{prefix}app.py",
            f"{prefix}.streamlit/config.toml",
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
        self.assertTrue(windows_launcher.isascii())
        self.assertIn(b"\r\n", windows_launcher)
        self.assertNotIn(b"\n", windows_launcher.replace(b"\r\n", b""))
        self.assertIn(b"startup.log", windows_launcher)
        self.assertIn(b"--server.address localhost", windows_launcher)
        self.assertIn(b"--server.showEmailPrompt false", windows_launcher)
        self.assertIn(b"--browser.gatherUsageStats false", windows_launcher)
        self.assertIn(b'>> "%LOG_FILE%" 2>&1', windows_launcher)

        streamlit_config = (ROOT / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("showEmailPrompt = false", streamlit_config)
        self.assertIn("gatherUsageStats = false", streamlit_config)


if __name__ == "__main__":
    unittest.main()
