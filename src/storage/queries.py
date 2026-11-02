"""Read-only query helpers over the SQLite warehouse.

Queries live in ``sql/`` so they can be reviewed and run by hand; this module
only binds parameters and normalizes the returned row.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT, get_db_path
from .db import get_conn


ACCEPTANCE_SQL_PATH = PROJECT_ROOT / "sql" / "acceptance_recent_7d_avg.sql"
DEFAULT_DAYS = 7


def _date_id(value: Any) -> str:
    """Normalize a date-like value to the warehouse ``YYYY-MM-DD`` contract."""

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value).strip()).isoformat()


def _latest_date_id(connection, name: str) -> str | None:
    """Return the newest ``date_id`` that has a price row for ``name``."""

    row = connection.execute(
        "SELECT MAX(f.date_id) "
        "FROM fact_price AS f "
        "JOIN dim_commodity AS c ON c.commodity_id = f.commodity_id "
        "WHERE c.name = ?",
        (name,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def recent_avg_price(
    name: str,
    *,
    as_of: str | date | datetime | None = None,
    days: int = DEFAULT_DAYS,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Average price over the latest ``days`` trading days for one commodity.

    ``as_of`` is inclusive and defaults to the commodity's newest ``date_id``
    in the database. When there is no matching data the result still has the
    requested ``name`` and ``as_of`` but reports ``days == 0`` and
    ``avg_price is None``.
    """

    commodity = str(name).strip()
    if not commodity:
        raise ValueError("name 不能为空")
    window = int(days)
    if window <= 0:
        raise ValueError("days 必须为正整数")

    path = get_db_path() if db_path is None else Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"SQLite 数据库不存在: {path}；先运行 python -m src.storage.init_db"
        )

    sql = ACCEPTANCE_SQL_PATH.read_text(encoding="utf-8")
    connection = get_conn(path)
    try:
        effective_as_of = (
            _latest_date_id(connection, commodity)
            if as_of is None
            else _date_id(as_of)
        )
        row = connection.execute(
            sql,
            {"name": commodity, "as_of": effective_as_of, "days": window},
        ).fetchone()
    finally:
        connection.close()

    return {
        "name": commodity,
        "avg_price": None if row[1] is None else float(row[1]),
        "days": int(row[2] or 0),
        "as_of": effective_as_of,
    }
