"""Load and link the V2.0 plant-to-vegetable mapping table.

This module owns mapping validation only. Scoring and optimization deliberately
stay outside this batch so that the mapping can be reused by later models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "data" / "plants.csv"

REQUIRED_COLUMNS = (
    "name",
    "vegetable_name",
    "sun_cost",
    "attack",
    "defense",
    "production",
    "control",
    "special_ability",
    "role",
)
RATING_COLUMNS = ("defense", "production", "control")


def load_plant_mapping(path: Path | str = DEFAULT_MAPPING_PATH) -> pd.DataFrame:
    """Read the canonical plant mapping and validate its contract."""

    mapping = pd.read_csv(path)
    validate_plant_mapping(mapping)
    return mapping


def validate_plant_mapping(mapping: pd.DataFrame) -> None:
    """Raise ``ValueError`` when a plant mapping violates the V2 contract."""

    missing = [column for column in REQUIRED_COLUMNS if column not in mapping.columns]
    if missing:
        raise ValueError(f"植物映射缺少字段: {', '.join(missing)}")

    if not 12 <= len(mapping) <= 15:
        raise ValueError("植物映射必须包含 12-15 种植物")
    if mapping["name"].duplicated().any():
        duplicates = mapping.loc[mapping["name"].duplicated(), "name"].tolist()
        raise ValueError(f"植物名不能重复: {', '.join(duplicates)}")

    text_columns: Iterable[str] = (
        "name",
        "vegetable_name",
        "special_ability",
        "role",
    )
    for column in text_columns:
        values = mapping[column].fillna("").astype(str).str.strip()
        if values.eq("").any():
            raise ValueError(f"字段 {column} 不能包含空值")

    for column in ("sun_cost", "attack", *RATING_COLUMNS):
        values = pd.to_numeric(mapping[column], errors="coerce")
        if values.isna().any() or values.lt(0).any():
            raise ValueError(f"字段 {column} 必须是非负数")

    for column in RATING_COLUMNS:
        if pd.to_numeric(mapping[column]).gt(10).any():
            raise ValueError(f"字段 {column} 必须在 0-10 范围内")


def link_plants_to_prices(
    mapping: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    require_all: bool = True,
) -> pd.DataFrame:
    """Join plants to V2 ``name`` prices or the legacy ``product`` fallback.

    The temporary ``product`` compatibility keeps this batch independently
    testable before the batch-2 cleaner changes prices to the V2 field name.
    """

    validate_plant_mapping(mapping)
    price_name_column = "name" if "name" in prices.columns else "product"
    if price_name_column not in prices.columns:
        raise ValueError("菜价数据必须包含 name 字段（兼容旧 product 字段）")

    price_data = prices.copy().rename(columns={price_name_column: "price_name"})
    price_data["price_name"] = price_data["price_name"].astype(str).str.strip()
    plant_data = mapping.copy()
    plant_data["vegetable_name"] = plant_data["vegetable_name"].str.strip()

    linked = plant_data.merge(
        price_data,
        how="left",
        left_on="vegetable_name",
        right_on="price_name",
        indicator=True,
    )
    if require_all:
        unmatched = linked.loc[linked["_merge"] == "left_only", "name"].unique()
        if len(unmatched):
            raise ValueError(f"以下植物没有对应菜价: {', '.join(unmatched)}")

    return linked.drop(columns="_merge").reset_index(drop=True)
