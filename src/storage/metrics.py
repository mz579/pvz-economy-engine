"""P1-1: recompute price metrics with SQL window functions.

The queries live in ``sql/metrics.sql`` so they can be reviewed and run by
hand. This module only loads a named statement, binds the connection and
normalizes the returned frame. It is a cross-check/demo companion to
:func:`src.features.add_price_features`; it does not change the business
feature definitions used by the pipeline.

Usage::

    python -m src.storage.metrics --db data/pvz.db
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import PROJECT_ROOT, get_db_path
from .db import get_conn


METRICS_SQL_PATH = PROJECT_ROOT / "sql" / "metrics.sql"
QUERY_MARKER = "-- query:"

METRIC_COLUMNS = (
    "date_id",
    "name",
    "commodity_id",
    "price",
    "ma7",
    "ma14",
    "ma30",
    "price_rank",
)
CONSECUTIVE_COLUMNS = ("commodity_id", "name", "days")


def _load_queries(path: str | Path = METRICS_SQL_PATH) -> dict[str, str]:
    """Split ``metrics.sql`` into ``{name: statement}`` using marker comments."""

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(QUERY_MARKER):
            current = stripped[len(QUERY_MARKER) :].strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)

    queries: dict[str, str] = {}
    for name, lines in sections.items():
        statement = "\n".join(lines).strip()
        if statement.endswith(";"):
            statement = statement[:-1].strip()
        if statement:
            queries[name] = statement
    return queries


def _resolve_path(db_path: str | Path | None) -> Path:
    return get_db_path() if db_path is None else Path(db_path).resolve()


def _read_query(
    query_name: str,
    columns: tuple[str, ...],
    db_path: str | Path | None,
) -> pd.DataFrame:
    """Execute one named query and return it with a stable column order."""

    path = _resolve_path(db_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"SQLite 数据库不存在: {path}；先运行 python -m src.storage.init_db"
        )

    queries = _load_queries()
    if query_name not in queries:
        raise KeyError(f"sql/metrics.sql 缺少查询: {query_name}")

    connection = get_conn(path)
    try:
        frame = pd.read_sql_query(queries[query_name], connection)
    finally:
        connection.close()

    return frame.loc[:, list(columns)]


def compute_metrics(db_path: str | Path | None = None) -> pd.DataFrame:
    """Return per-row price metrics computed with SQL window functions.

    Columns: ``date_id, name, commodity_id, price, ma7, ma14, ma30,
    price_rank`` sorted by ``name`` then ``date_id``. ``price_rank`` is the
    same-day cross-commodity rank (1 = most expensive), per plan section 4.4.
    """

    frame = _read_query("price_metrics", METRIC_COLUMNS, db_path)
    return frame.sort_values(["name", "date_id"]).reset_index(drop=True)


def max_consecutive_up_days(db_path: str | Path | None = None) -> pd.DataFrame:
    """Return ``commodity_id, name, days`` for each commodity.

    ``days`` is the length (in days) of the longest run of strictly increasing
    prices; a commodity with no increase reports ``0``.
    """

    frame = _read_query(
        "max_consecutive_up_days", CONSECUTIVE_COLUMNS, db_path
    )
    frame["days"] = frame["days"].astype(int)
    return frame.sort_values(["name"]).reset_index(drop=True)


def _format(frame: pd.DataFrame) -> str:
    return frame.to_string(index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="用 SQL 窗口函数重算价格指标（与 Pandas 互校/演示）。"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite 数据库路径，默认为配置文件中的 db.path",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=10,
        help="每段结果打印的行数（默认 10）",
    )
    args = parser.parse_args(argv)

    metrics = compute_metrics(args.db)
    consecutive = max_consecutive_up_days(args.db)

    print("== 价格指标（SQL 窗口函数）==")
    print(_format(metrics.head(args.rows)))
    print()
    print("== 最长连续上涨天数 ==")
    print(_format(consecutive.head(args.rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
