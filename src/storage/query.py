"""CLI: ``python -m src.storage.query --name 土豆 --days 7``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .queries import DEFAULT_DAYS, recent_avg_price


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询某品类最近 N 个交易日均价")
    parser.add_argument("--name", required=True, help="品类名称，例如 土豆")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"交易日窗口（默认 {DEFAULT_DAYS}）",
    )
    parser.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        help="截止日期 YYYY-MM-DD（默认取该品类最新日期）",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite 路径（默认使用 config.yaml 中的 db.path）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = recent_avg_price(
            args.name,
            as_of=args.as_of,
            days=args.days,
            db_path=args.db,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误: {exc}")
        return 1

    print(f"品类: {result['name']}")
    print(f"截止日期: {result['as_of'] or '无数据'}")
    print(f"最近 {args.days} 个交易日: 实际 {result['days']} 天")
    if result["days"] == 0 or result["avg_price"] is None:
        print("均价: 无数据")
    else:
        print(f"均价: {result['avg_price']:.2f} 元/kg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
