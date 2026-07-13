"""Cleaning and schema normalization for vegetable price records."""

from __future__ import annotations

from typing import Iterable

import pandas as pd


STANDARD_COLUMNS = ("date", "name", "price", "source")

COLUMN_ALIASES = {
    "日期": "date",
    "发布日期": "date",
    "product": "name",
    "product_name": "name",
    "品种": "name",
    "品名": "name",
    "蔬菜": "name",
    "avg_price": "price",
    "平均价": "price",
    "均价": "price",
    "价格": "price",
    "数据来源": "source",
    "单位": "unit",
}

PRODUCT_ALIAS: dict[str, tuple[str, ...]] = {
    "大白菜": ("白菜", "黄芽白", "结球白菜"),
    "土豆": ("马铃薯", "洋芋", "马铃薯(土豆)"),
    "西红柿": ("番茄", "番茄(西红柿)"),
    "黄瓜": ("青瓜", "胡瓜"),
    "油菜": ("小油菜", "青菜", "上海青"),
    "豌豆": ("青豌豆", "荷兰豆"),
    "大蒜": ("蒜头", "大蒜(蒜头)"),
    "生菜": ("叶用莴苣", "团生菜"),
    "菠菜": ("波斯菜", "赤根菜"),
    "芹菜": ("旱芹", "药芹", "香芹"),
}


def _map_product_alias(value: object) -> str:
    name = str(value).strip()
    for standard, aliases in PRODUCT_ALIAS.items():
        if name == standard or name in aliases:
            return standard
    return name


def _require_columns(columns: Iterable[str]) -> None:
    missing = set(STANDARD_COLUMNS[:3]).difference(columns)
    if missing:
        raise ValueError(f"菜价数据缺少字段: {', '.join(sorted(missing))}")


def clean_price_data(
    data: pd.DataFrame,
    *,
    source_name: str | None = None,
) -> pd.DataFrame:
    """Return prices using the V2 contract: date, name, price, source.

    Dates are normalized to day precision and prices to yuan per kilogram.
    Rows with invalid dates, blank names, or non-positive prices are removed.
    """

    if data.empty:
        return pd.DataFrame(columns=list(STANDARD_COLUMNS))

    result = data.copy().rename(columns=COLUMN_ALIASES)
    _require_columns(result.columns)

    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.normalize()
    result["name"] = result["name"].map(_map_product_alias)
    result["price"] = pd.to_numeric(result["price"], errors="coerce")

    if "unit" in result.columns:
        unit = result["unit"].fillna("").astype(str)
        yuan_per_jin = unit.str.contains("斤", regex=False)
        result.loc[yuan_per_jin, "price"] = result.loc[yuan_per_jin, "price"] * 2

    if source_name:
        result["source"] = source_name
    elif "source" not in result.columns:
        result["source"] = "unknown"
    result["source"] = result["source"].fillna("unknown").astype(str).str.strip()

    valid = (
        result["date"].notna()
        & result["name"].ne("")
        & result["price"].notna()
        & result["price"].gt(0)
    )
    result = result.loc[valid, list(STANDARD_COLUMNS)].copy()
    result["price"] = result["price"].round(4)
    result = (
        result.groupby(["date", "name", "source"], as_index=False, sort=True)["price"]
        .mean()
        .loc[:, list(STANDARD_COLUMNS)]
    )
    return result.sort_values(["name", "date", "source"]).reset_index(drop=True)


def standardize_price_data(
    data: pd.DataFrame,
    source_name: str | None = None,
) -> pd.DataFrame:
    """Backward-compatible entry point for the V2 cleaner."""

    return clean_price_data(data, source_name=source_name)


def add_time_features(data: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper; feature engineering lives in ``src.features``."""

    from src.features import add_price_features

    return add_price_features(data)


def compute_region_stability(data: pd.DataFrame) -> float:
    """Mean coefficient of variation across vegetables (lower is steadier)."""

    cleaned = clean_price_data(data)
    grouped = cleaned.groupby("name")["price"]
    means = grouped.mean().replace(0, pd.NA)
    coefficients = grouped.std(ddof=0).div(means).fillna(0)
    return float(coefficients.mean())
