"""SQLite connection helpers and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import PROJECT_ROOT, get_db_path


SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


def _resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Return an explicit test path, or the configured default database path."""

    return get_db_path() if db_path is None else Path(db_path).resolve()


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled.

    The parent directory is created on demand so a fresh checkout can build the
    database without any manual setup.
    """

    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path | None = None) -> Path:
    """Create the P0-B1 tables from ``sql/schema.sql`` and return the path."""

    path = _resolve_db_path(db_path)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_conn(path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
    return path
