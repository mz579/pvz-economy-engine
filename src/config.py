"""Central configuration loading for the V2.0 project.

Configuration lives in ``config.yaml`` at the project root. Relative paths in
that file are resolved against the project root so behaviour does not depend on
the directory the process was started from.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Used when config.yaml is absent, and as the fallback for missing keys.
DEFAULT_CONFIG: dict[str, Any] = {
    "db": {"path": "data/pvz.db"},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` in place."""

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load ``config.yaml`` merged over the built-in defaults.

    ``config_path`` is mainly intended for tests. When omitted, the project
    root copy is used. An explicitly supplied path must exist, so callers do
    not silently test against defaults by accident.
    """

    path = (
        Path(config_path).resolve()
        if config_path is not None
        else DEFAULT_CONFIG_PATH
    )
    config = deepcopy(DEFAULT_CONFIG)

    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"配置文件必须是 YAML 映射: {path}")
        _merge(config, loaded)
    elif config_path is not None:
        raise FileNotFoundError(f"配置文件不存在: {path}")

    return config


def resolve_project_path(
    value: str | Path, *, root: str | Path = PROJECT_ROOT
) -> Path:
    """Resolve a possibly-relative path against the project root."""

    path = Path(value)
    if path.is_absolute():
        return path
    return (Path(root).resolve() / path).resolve()


def get_db_path(config: dict[str, Any] | None = None) -> Path:
    """Return the SQLite database path declared in configuration."""

    settings = config if config is not None else load_config()
    db_settings = settings.get("db")
    if not isinstance(db_settings, dict):
        db_settings = {}
    raw_path = db_settings.get("path") or DEFAULT_CONFIG["db"]["path"]
    return resolve_project_path(raw_path)
