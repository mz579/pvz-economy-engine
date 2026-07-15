"""Build the portable source release used by GitHub Releases."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime import RUNTIME_REQUIRED_FILES, require_runtime_files

TOP_LEVEL_FILES = (
    "app.py",
    "cli.py",
    "README.md",
    "README_FIRST.txt",
    "RELEASE_NOTES.md",
    "requirements.txt",
    "start_windows.bat",
    "start_unix.sh",
)
INCLUDED_DIRECTORIES = (
    ".streamlit",
    "assets",
    "src",
    "data/fallback",
    "data/templates",
    "docs/screenshots",
)
IGNORED_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def build_release(version: str, output_directory: Path) -> Path:
    """Create a small, reproducible ZIP with code, sample data and launchers."""

    normalized_version = version.strip() or "v2.1.2"
    folder_name = f"pvz-economy-engine-{normalized_version}"
    output_directory.mkdir(parents=True, exist_ok=True)
    archive_path = output_directory / f"{folder_name}-portable.zip"

    files: list[Path] = list(require_runtime_files(ROOT))
    for relative in TOP_LEVEL_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"Release 缺少必要文件: {relative}")
        files.append(path)
    for relative in INCLUDED_DIRECTORIES:
        directory = ROOT / relative
        if not directory.is_dir():
            continue
        files.extend(path for path in directory.rglob("*") if _should_include(path))

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(set(files)):
            relative = path.relative_to(ROOT).as_posix()
            archive_name = f"{folder_name}/{relative}"
            if path.suffix.lower() == ".bat":
                # cmd.exe is fussy about launcher encoding and line endings.
                # Normalize the release copy even when Actions builds on Linux.
                content = path.read_text(encoding="ascii").replace("\r\n", "\n")
                archive.writestr(archive_name, content.replace("\n", "\r\n"))
            else:
                archive.write(path, archive_name)
    _validate_release_archive(archive_path, folder_name)
    return archive_path


def _should_include(path: Path) -> bool:
    return (
        path.is_file()
        and not any(part in IGNORED_NAMES for part in path.parts)
        and path.suffix.lower() not in IGNORED_SUFFIXES
    )


def _validate_release_archive(archive_path: Path, folder_name: str) -> None:
    """Fail the build if a required runtime file did not reach the ZIP."""

    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    missing = [
        relative_path
        for relative_path in RUNTIME_REQUIRED_FILES
        if f"{folder_name}/{relative_path}" not in names
    ]
    if missing:
        archive_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Release ZIP 缺少必要运行文件: " + ", ".join(missing)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 PvZ Economy Engine Release ZIP")
    parser.add_argument("--version", default="v2.1.2")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    archive = build_release(args.version, args.output)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
