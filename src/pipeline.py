"""Runnable collection -> cleaning -> feature pipeline for V2.0."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.crawler import (
    DEFAULT_FALLBACK_PATH,
    CollectionResult,
    collect_price_data,
    load_local_fallback,
)
from src.features import add_price_features
from src.preprocess import NORMALIZED_PRICE_UNIT, clean_price_data
from src.runtime import runtime_path


DEFAULT_RAW_PATH = runtime_path("data/raw/latest_prices.csv")
DEFAULT_METADATA_PATH = runtime_path("data/raw/latest_prices.metadata.json")
DEFAULT_PROCESSED_PATH = runtime_path("data/processed/vegetable_prices.csv")
DEFAULT_PLANT_PATH = runtime_path("data/plants.csv")


@dataclass(frozen=True)
class PipelineArtifacts:
    data: pd.DataFrame
    raw_path: Path
    processed_path: Path
    metadata_path: Path
    collection: CollectionResult


def run_data_pipeline(
    *,
    prefer_network: bool = True,
    fallback_path: Path | str = DEFAULT_FALLBACK_PATH,
    raw_path: Path | str = DEFAULT_RAW_PATH,
    processed_path: Path | str = DEFAULT_PROCESSED_PATH,
    metadata_path: Path | str = DEFAULT_METADATA_PATH,
    history_window: int = 30,
    timeout: float = 8.0,
) -> PipelineArtifacts:
    """Run the complete, offline-safe data preparation pipeline."""

    raw_target = Path(raw_path)
    processed_target = Path(processed_path)
    metadata_target = Path(metadata_path)
    for target in (raw_target, processed_target, metadata_target):
        target.parent.mkdir(parents=True, exist_ok=True)

    collection = collect_price_data(
        prefer_network=prefer_network,
        fallback_path=fallback_path,
        timeout=timeout,
    )
    cleaned = clean_price_data(collection.data)
    if cleaned.empty:
        raise ValueError("清洗后没有可用菜价记录")
    required_names = _required_vegetable_names()
    missing_names = required_names.difference(cleaned["name"].unique())
    if missing_names and not collection.used_fallback:
        online_source = collection.source
        fallback_raw = load_local_fallback(fallback_path)
        cleaned = clean_price_data(fallback_raw)
        collection = CollectionResult(
            data=fallback_raw,
            source="local_csv_fallback",
            used_fallback=True,
            message=(
                f"{online_source} 未覆盖映射蔬菜 "
                f"{', '.join(sorted(missing_names))}，已回退本地 CSV。"
            ),
            source_url=str(Path(fallback_path)),
        )
    remaining_missing = required_names.difference(cleaned["name"].unique())
    if remaining_missing:
        raise ValueError(
            f"菜价数据无法覆盖植物映射: {', '.join(sorted(remaining_missing))}"
        )

    collection.data.to_csv(raw_target, index=False, encoding="utf-8-sig")
    featured = add_price_features(cleaned, history_window=history_window)
    featured.to_csv(
        processed_target,
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%d",
    )

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": collection.source,
        "source_url": collection.source_url,
        "used_fallback": collection.used_fallback,
        "message": collection.message,
        "rows": int(len(featured)),
        "vegetables": int(featured["name"].nunique()),
        "date_min": featured["date"].min().strftime("%Y-%m-%d"),
        "date_max": featured["date"].max().strftime("%Y-%m-%d"),
        "price_unit": NORMALIZED_PRICE_UNIT,
        "history_window_days": history_window,
    }
    metadata_target.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return PipelineArtifacts(
        data=featured,
        raw_path=raw_target,
        processed_path=processed_target,
        metadata_path=metadata_target,
        collection=collection,
    )


def load_or_build_processed_prices(
    path: Path | str = DEFAULT_PROCESSED_PATH,
    *,
    prefer_network: bool = False,
) -> pd.DataFrame:
    """Load processed data, generating it from fallback when absent."""

    target = Path(path)
    if not target.is_file():
        data = run_data_pipeline(
            prefer_network=prefer_network,
            processed_path=target,
        ).data
    else:
        data = pd.read_csv(target, parse_dates=["date"])
        required = {"date", "name", "price", "source", "historical_mean", "volatility"}
        missing = required.difference(data.columns)
        missing_names = _required_vegetable_names().difference(data.get("name", []))
        if missing or missing_names:
            data = run_data_pipeline(
                prefer_network=prefer_network,
                processed_path=target,
            ).data
        else:
            data.attrs["price_unit"] = NORMALIZED_PRICE_UNIT
    data_days_old = (date.today() - data["date"].max().date()).days
    data.attrs["data_days_old"] = data_days_old
    return data


def _required_vegetable_names(path: Path | str = DEFAULT_PLANT_PATH) -> set[str]:
    mapping = pd.read_csv(path, usecols=["vegetable_name"])
    return set(mapping["vegetable_name"].dropna().astype(str).str.strip())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 V2 统一菜价特征文件")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--online", action="store_true", help="优先尝试新发地公开数据")
    mode.add_argument("--offline", action="store_true", help="仅使用本地 CSV fallback")
    parser.add_argument("--output", type=Path, default=DEFAULT_PROCESSED_PATH)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    artifacts = run_data_pipeline(
        prefer_network=bool(args.online and not args.offline),
        processed_path=args.output,
    )
    print(artifacts.collection.message)
    print(
        f"processed={artifacts.processed_path} rows={len(artifacts.data)} "
        f"vegetables={artifacts.data['name'].nunique()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
