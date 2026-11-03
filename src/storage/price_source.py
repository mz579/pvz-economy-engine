"""Read dashboard-ready price features from the SQLite warehouse.

The dashboard needs one row per commodity (latest price plus a short history
summary).  This module is intentionally read-only: a missing database, an
empty warehouse or a schema-less file all degrade to ``None`` so callers can
fall back to the offline CSV instead of failing.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from ..config import get_db_path
from ..preprocess import NORMALIZED_PRICE_UNIT


FEATURE_COLUMNS = (
    "date",
    "name",
    "price",
    "source",
    "historical_mean",
    "volatility",
)
HISTORY_WINDOW = 30


def _resolve_path(db_path: str | Path | None) -> Path:
    """Return the configured database path when no explicit path is given."""

    return get_db_path() if db_path is None else Path(db_path).resolve()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    """Open an existing database through SQLite's read-only URI mode."""

    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _summarize(prices: list[float]) -> tuple[float, float]:
    """Return ``(mean, coefficient_of_variation)`` for the latest window.

    ``volatility`` is the population standard deviation (``ddof=0``) divided
    by the mean.  It is reported as ``0`` when the window is too short or the
    mean is not positive, so downstream scoring never sees ``inf``/``NaN``.
    """

    if not prices:
        return 0.0, 0.0
    mean = sum(prices) / len(prices)
    if len(prices) < 2 or mean <= 0:
        return float(mean), 0.0
    variance = sum((price - mean) ** 2 for price in prices) / len(prices)
    return float(mean), float((variance ** 0.5) / mean)


def load_price_features_from_db(
    db_path: str | Path | None = None,
) -> pd.DataFrame | None:
    """Return the latest price features per commodity, or ``None``.

    Each row contains the commodity's newest ``date``/``price``/``source`` and
    the mean/volatility of its most recent :data:`HISTORY_WINDOW` prices.
    A missing database or an empty ``fact_price`` table returns ``None``.
    """

    path = _resolve_path(db_path)
    if not path.is_file():
        return None

    try:
        connection = _connect_readonly(path)
    except sqlite3.Error:
        return None

    try:
        rows = connection.execute(
            "SELECT c.name, f.date_id, f.price, COALESCE(f.source, 'unknown') "
            "FROM fact_price AS f "
            "JOIN dim_commodity AS c ON c.commodity_id = f.commodity_id "
            "ORDER BY c.name ASC, f.date_id DESC"
        ).fetchall()
    except sqlite3.Error:
        # A present but uninitialised file has no warehouse schema.
        return None
    finally:
        connection.close()

    if not rows:
        return None

    # Newest first per commodity, so ``items[0]`` is the latest observation
    # and ``items[:HISTORY_WINDOW]`` is the recent history window.
    grouped: dict[str, list[tuple[str, float, str]]] = {}
    for name, date_id, price, source in rows:
        grouped.setdefault(str(name), []).append(
            (str(date_id), float(price), str(source))
        )

    records: list[dict[str, object]] = []
    for name, items in grouped.items():
        date_id, latest_price, source = items[0]
        window = [price for _, price, _ in items[:HISTORY_WINDOW]]
        historical_mean, volatility = _summarize(window)
        records.append(
            {
                "date": date_id,
                "name": name,
                "price": latest_price,
                "source": source,
                "historical_mean": historical_mean,
                "volatility": volatility,
            }
        )

    frame = pd.DataFrame(records, columns=list(FEATURE_COLUMNS))
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in ("price", "historical_mean", "volatility"):
        frame[column] = frame[column].astype(float)
    frame = frame.sort_values("name").reset_index(drop=True)

    frame.attrs["price_unit"] = NORMALIZED_PRICE_UNIT
    latest = frame["date"].max()
    frame.attrs["data_days_old"] = (
        int((date.today() - latest.date()).days) if pd.notna(latest) else 0
    )
    return frame
