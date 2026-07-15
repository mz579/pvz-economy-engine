"""Acceptance tests for the downloadable local release package."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_release import TOP_LEVEL_FILES, build_release
from src.runtime import RUNTIME_REQUIRED_FILES


class ReleasePackageTests(unittest.TestCase):
    def test_portable_zip_contains_runtime_and_region_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = build_release("v2.1.2-test", Path(temporary))
            self.assertTrue(archive.is_file())
            with ZipFile(archive) as package:
                names = set(package.namelist())
                windows_launcher = package.read(
                    "pvz-economy-engine-v2.1.2-test/start_windows.bat"
                )

        prefix = "pvz-economy-engine-v2.1.2-test/"
        expected = {
            f"{prefix}app.py",
            f"{prefix}.streamlit/config.toml",
            f"{prefix}README_FIRST.txt",
            f"{prefix}requirements.txt",
            f"{prefix}start_windows.bat",
            f"{prefix}start_unix.sh",
            f"{prefix}src/scoring.py",
            f"{prefix}src/user_data.py",
            f"{prefix}src/runtime.py",
            f"{prefix}data/plants.csv",
            f"{prefix}data/fallback/vegetable_prices.csv",
            f"{prefix}data/templates/regional_prices_template.csv",
            f"{prefix}docs/screenshots/dashboard.png",
        }
        self.assertTrue(expected.issubset(names))
        self.assertTrue(
            {f"{prefix}{path}" for path in RUNTIME_REQUIRED_FILES}.issubset(names)
        )
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

    def test_build_fails_for_each_missing_required_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "package-root"
            output = Path(temporary) / "dist"
            scaffold = set(TOP_LEVEL_FILES).union(RUNTIME_REQUIRED_FILES)
            for relative_path in scaffold:
                path = package_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")

            for missing_relative_path in RUNTIME_REQUIRED_FILES:
                missing_path = package_root / missing_relative_path
                missing_path.unlink()
                with self.subTest(path=missing_relative_path):
                    with patch("scripts.build_release.ROOT", package_root):
                        with self.assertRaisesRegex(
                            FileNotFoundError,
                            re.escape(missing_relative_path),
                        ):
                            build_release("v2.1.2-broken", output)
                missing_path.write_bytes(b"")

    def test_extracted_cli_runs_outside_package_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = build_release("v2.1.2-outside", root / "dist")
            extract_root = root / "extract"
            with ZipFile(archive) as package:
                package.extractall(extract_root)

            package_root = extract_root / "pvz-economy-engine-v2.1.2-outside"
            outside_directory = root / "outside-working-directory"
            outside_directory.mkdir()
            processed_output = outside_directory / "processed.csv"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(package_root / "cli.py"),
                    "--sun",
                    "150",
                    "--cells",
                    "20",
                    "--top",
                    "1",
                    "--processed-output",
                    str(processed_output),
                ],
                cwd=outside_directory,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
            self.assertIn(b"Status: Optimal", completed.stdout)
            self.assertTrue(processed_output.is_file())


if __name__ == "__main__":
    unittest.main()
