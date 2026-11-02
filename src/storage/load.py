"""Idempotent loading of cleaned prices into the SQLite warehouse.

The loader is deliberately conservative: it only inserts/updates the three
dimension/fact tables plus the ETL watermark, and it commits as a single unit
so a failed batch never leaves partially loaded prices behind.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .db import get_conn, init_db


PRICE_PIPELINE = "price_pipeline"
REQUIRED_COLUMNS = ("date", "name", "price")


def _date_id(value: Any) -> str:
    """Normalize a date-like value to the warehouse ``YYYY-MM-DD`` contract."""

    parsed = pd.to_datetime(value, errors="raise")
    if pd.isna(parsed):
        raise ValueError(f"无效日期: {value!r}")
    return parsed.strftime("%Y-%m-%d")


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _open_connection(
    conn: sqlite3.Connection | None, db_path: str | Path | None
) -> tuple[sqlite3.Connection, bool]:
    """Return ``(connection, owned)``; caller-provided connections are reused.

    When the loader owns the connection it also ensures the schema exists, so a
    one-off ``load_prices`` call works against a fresh database file.
    """

    if conn is not None:
        return conn, False
    path = init_db(db_path)
    return get_conn(path), True


def load_prices(
    df: pd.DataFrame,
    *,
    conn: sqlite3.Connection | None = None,
    db_path: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Upsert cleaned prices and return batch statistics.

    ``df`` must contain ``date``, ``name`` and ``price``; ``source`` is
    optional. Loading the same rows twice is a no-op for row counts because
    ``dim_date`` and ``fact_price`` use their natural keys. ``run_id`` is
    accepted for call-site symmetry; run metadata is written by
    :func:`record_run`.
    """

    del run_id  # The run record is written explicitly by record_run().

    if df is None:
        raise ValueError("df 不能为空")
    frame = pd.DataFrame(df)
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"菜价数据缺少字段: {', '.join(sorted(missing))}")

    rows_in = int(len(frame))
    if rows_in == 0:
        return {
            "rows_in": 0,
            "prices_upserted": 0,
            "commodities": 0,
            "date_min": None,
            "date_max": None,
        }

    has_source = "source" in frame.columns

    # De-duplicate by the fact table's natural key. Later rows win, mirroring
    # an upsert where the last write for a day/commodity is authoritative.
    records: dict[tuple[str, str], tuple[float, str]] = {}
    for _, row in frame.iterrows():
        date_id = _date_id(row["date"])
        name = str(row["name"]).strip()
        if not name:
            raise ValueError("菜价数据包含空名称")
        price = float(row["price"])
        if has_source and not pd.isna(row["source"]):
            source = str(row["source"]).strip()
        else:
            source = "unknown"
        records[(date_id, name)] = (price, source)

    date_ids = sorted({date_id for date_id, _ in records})
    names = sorted({name for _, name in records})

    connection, owned = _open_connection(conn, db_path)
    try:
        # Dimensions: dates are immutable for a given date_id.
        for date_id in date_ids:
            day = date.fromisoformat(date_id)
            connection.execute(
                "INSERT INTO dim_date (date_id, year, month, day, weekday) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(date_id) DO NOTHING",
                (date_id, day.year, day.month, day.day, day.weekday()),
            )

        # Commodities: get-or-create by the UNIQUE(name) natural key.
        commodity_ids: dict[str, int] = {}
        for name in names:
            row = connection.execute(
                "SELECT commodity_id FROM dim_commodity WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO dim_commodity (name) VALUES (?)", (name,)
                )
                commodity_ids[name] = int(cursor.lastrowid)
            else:
                commodity_ids[name] = int(row[0])

        for (date_id, name), (price, source) in records.items():
            connection.execute(
                "INSERT INTO fact_price (date_id, commodity_id, price, source) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(date_id, commodity_id) DO UPDATE SET "
                "price = excluded.price, source = excluded.source",
                (date_id, commodity_ids[name], price, source),
            )

        updated_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO etl_watermark (pipeline, last_date_id, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(pipeline) DO UPDATE SET "
            "last_date_id = excluded.last_date_id, "
            "updated_at = excluded.updated_at",
            (PRICE_PIPELINE, date_ids[-1], updated_at),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if owned:
            connection.close()

    return {
        "rows_in": rows_in,
        "prices_upserted": len(records),
        "commodities": len(names),
        "date_min": date_ids[0],
        "date_max": date_ids[-1],
    }


def record_run(
    run_id: str,
    stage: str,
    status: str,
    rows_in: int | None = None,
    rows_out: int | None = None,
    started_at: datetime | str | None = None,
    finished_at: datetime | str | None = None,
    *,
    conn: sqlite3.Connection | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Insert or update one pipeline run, keyed by ``run_id``."""

    connection, owned = _open_connection(conn, db_path)
    try:
        connection.execute(
            "INSERT INTO pipeline_run "
            "(run_id, stage, started_at, finished_at, rows_in, rows_out, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "stage = excluded.stage, "
            "started_at = excluded.started_at, "
            "finished_at = excluded.finished_at, "
            "rows_in = excluded.rows_in, "
            "rows_out = excluded.rows_out, "
            "status = excluded.status",
            (
                str(run_id),
                str(stage),
                _timestamp(started_at),
                _timestamp(finished_at),
                rows_in,
                rows_out,
                str(status),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if owned:
            connection.close()
