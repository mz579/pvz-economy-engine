"""Compatibility entry point: ``python -m src.storage.init_db``."""

from __future__ import annotations

from .__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
