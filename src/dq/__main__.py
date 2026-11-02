"""CLI: ``python -m src.dq --csv <processed.csv> [--db <db>]``."""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.storage.load import latest_successful_row_count, record_dq

from .rules import validate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="对清洗后的菜价 CSV 运行数据质量校验（R1-R7）"
    )
    parser.add_argument("--csv", type=Path, required=True, help="待校验的 CSV 文件")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite 数据库路径（默认使用配置中的 data/pvz.db）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    frame = pd.read_csv(args.csv)
    prev_row_count = latest_successful_row_count(db_path=args.db)
    result = validate(frame, prev_row_count=prev_row_count)

    run_id = uuid4().hex
    record_dq(run_id, result.records, db_path=args.db)

    for record in result.records:
        print(
            f"[{record['rule']}] {record['status']:<4} "
            f"({record['severity']}) {record['detail']}"
        )
    print(f"run_id={run_id} rows={len(frame)} passed={result.passed}")
    if result.warnings:
        print(f"警告 {len(result.warnings)} 条，不影响落库")
    if result.errors:
        print(f"阻断 {len(result.errors)} 条，拒绝落库")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
