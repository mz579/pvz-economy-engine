"""Build the local SQLite database: ``python -m src.storage``."""

from __future__ import annotations

from .db import init_db


def main() -> int:
    path = init_db()
    print(f"SQLite schema initialized: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
