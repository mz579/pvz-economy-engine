"""Runtime resource paths and portable-package integrity checks."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Keep this manifest explicit: adding a new runtime dependency without packaging
# it must fail release tests instead of surprising users after download.
RUNTIME_REQUIRED_FILES = (
    ".streamlit/config.toml",
    "app.py",
    "cli.py",
    "requirements.txt",
    "start_unix.sh",
    "start_windows.bat",
    "assets/style.css",
    "data/plants.csv",
    "data/fallback/vegetable_prices.csv",
    "data/templates/regional_prices_template.csv",
    "src/__init__.py",
    "src/crawler.py",
    "src/dashboard.py",
    "src/features.py",
    "src/optimizer.py",
    "src/pipeline.py",
    "src/plant_mapping.py",
    "src/preprocess.py",
    "src/runtime.py",
    "src/scoring.py",
    "src/user_data.py",
)


def runtime_path(relative_path: str, *, root: Path | str = PROJECT_ROOT) -> Path:
    """Resolve a runtime resource from the project root, never from ``cwd``."""

    return (Path(root).resolve() / Path(relative_path)).resolve()


def find_missing_runtime_files(
    root: Path | str = PROJECT_ROOT,
) -> tuple[str, ...]:
    """Return relative paths for required files missing from one installation."""

    return tuple(
        relative_path
        for relative_path in RUNTIME_REQUIRED_FILES
        if not runtime_path(relative_path, root=root).is_file()
    )


def require_runtime_files(root: Path | str = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return absolute required paths or fail with a concise package error."""

    missing = find_missing_runtime_files(root)
    if missing:
        raise FileNotFoundError(
            "安装包缺少必要运行文件: " + ", ".join(missing)
        )
    return tuple(runtime_path(path, root=root) for path in RUNTIME_REQUIRED_FILES)
