"""SQLite storage layer for the P0 schema."""

from .db import get_conn, init_db
from .load import (
    latest_successful_row_count,
    load_prices,
    record_dq,
    record_run,
)
from .queries import recent_avg_price

# Lazy re-export so ``python -m src.storage.metrics`` does not import the
# module twice (which triggers a runpy RuntimeWarning).
_LAZY_EXPORTS = {"compute_metrics", "max_consecutive_up_days"}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        from . import metrics

        return getattr(metrics, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_conn",
    "init_db",
    "load_prices",
    "record_dq",
    "record_run",
    "latest_successful_row_count",
    "recent_avg_price",
    "compute_metrics",
    "max_consecutive_up_days",
]
