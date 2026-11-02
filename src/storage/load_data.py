"""Standalone loader: ``python -m src.storage.load_data``.

Reads the processed price CSV and upserts it into the local SQLite warehouse.
Useful for rebuilding ``fact_price`` from an existing processed file.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.runtime import runtime_path

from .load import PRICE_PIPELINE, load_prices, record_run


DEFAULT_PROCESSED_PATH = runtime_path("data/processed/vegetable_prices.csv")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将清洗后的菜价 CSV 落库")
    parser.add_argument("--csv", type=Path, default=DEFAULT_PROCESSED_PATH)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite 路径，默认使用 config.yaml 中的 db.path",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc)
    try:
        data = pd.read_csv(args.csv)
        stats = load_prices(data, db_path=args.db, run_id=run_id)
        record_run(
            run_id,
            PRICE_PIPELINE,
            "success",
            rows_in=stats["rows_in"],
            rows_out=stats["prices_upserted"],
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            db_path=args.db,
        )
    except Exception:
        try:
            record_run(
                run_id,
                PRICE_PIPELINE,
                "failed",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                db_path=args.db,
            )
        except Exception:
            # Never mask the original loading failure.
            pass
        raise

    print(
        f"loaded csv={args.csv} rows_in={stats['rows_in']} "
        f"prices_upserted={stats['prices_upserted']} "
        f"commodities={stats['commodities']} "
        f"date_range={stats['date_min']}..{stats['date_max']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
