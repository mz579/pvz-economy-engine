# -*- coding: utf-8 -*-
"""Data standardization and feature engineering module.

Standardizes output from all adapters into a uniform time-series format,
including cross-region product alias mapping, missing value interpolation,
outlier removal, and time-series feature engineering.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np


PRODUCT_ALIAS: Dict[str, List[str]] = {
    "大白菜": ["白菜", "大白菜", "黄芽白", "结球白菜"],
    "土豆": ["马铃薯", "洋芋", "土豆", "马铃薯(土豆)"],
    "西红柿": ["番茄", "西红柿", "番茄(西红柿)", "钃寗"],
    "黄瓜": ["黄瓜", "青瓜", "胡瓜"],
    "茄子": ["茄子", "落苏", "昆仑瓜"],
    "大蒜": ["大蒜", "蒜头", "大蒜(蒜头)"],
    "菠菜": ["菠菜", "波斯菜", "赤根菜"],
    "生菜": ["生菜", "叶用莴苣", "团生菜"],
    "油菜": ["油菜", "小白菜", "青菜", "上海青"],
    "胡萝卜": ["胡萝卜", "红萝卜", "甘荀"],
    "芹菜": ["芹菜", "旱芹", "药芹", "香芹"],
    "豌豆": ["豌豆", "青豌豆", "荷兰豆"],
    "韭菜": ["韭菜", "韭", "起阳草"],
    "豆角": ["豆角", "四季豆", "菜豆", "芸豆", "扁豆"],
    "西兰花": ["西兰花", "青花菜", "花椰菜"],
    "苦瓜": ["苦瓜", "凉瓜"],
    "南瓜": ["南瓜", "倭瓜", "金瓜"],
    "冬瓜": ["冬瓜"],
}


def standardize_price_data(df: pd.DataFrame, source_name: Optional[str] = None) -> pd.DataFrame:
    """Convert raw adapter data to standard time-series format.

    Standard output columns: [date, product, price, source].
    Applies product alias mapping, missing value interpolation, and outlier removal.

    Args:
        df: Input DataFrame with date, product, price columns.
        source_name: Data source tag, keeps df source column if None.

    Returns:
        Standardized Pandas DataFrame.
    """
    if df.empty:
        return pd.DataFrame(columns=["date", "product", "price", "source"])

    result = df.copy()
    result["product"] = result["product"].apply(_map_product_alias)
    if source_name:
        result["source"] = source_name
    result = result.sort_values(["product", "date"]).reset_index(drop=True)
    result["price"] = result.groupby("product")["price"].transform(
        lambda s: s.interpolate(method="linear").bfill().ffill()
    )
    result = _remove_outliers(result)
    result["date"] = pd.to_datetime(result["date"])
    cols = [c for c in ["date", "product", "price", "source"] if c in result.columns]
    return result[cols].reset_index(drop=True)


def _map_product_alias(name: str) -> str:
    """Map alias to standard product name."""
    if not isinstance(name, str):
        return str(name)
    name = name.strip()
    for standard, aliases in PRODUCT_ALIAS.items():
        if name == standard or name in aliases:
            return standard
    return name


def _remove_outliers(df: pd.DataFrame, col: str = "price", sigma: float = 3.0) -> pd.DataFrame:
    """Remove outliers using the 3-sigma rule."""
    mean = df[col].mean()
    std = df[col].std()
    lower = mean - sigma * std
    upper = mean + sigma * std
    mask = (df[col] >= lower) & (df[col] <= upper)
    return df[mask].reset_index(drop=True)


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Generate time-series features: moving averages, volatility, price changes.

    Args:
        df: Standardized DataFrame with date, product, price columns.

    Returns:
        DataFrame with additional feature columns.
    """
    result = df.copy()
    result = result.sort_values(["product", "date"]).reset_index(drop=True)

    for w in [7, 14, 30]:
        result[f"price_ma{w}"] = result.groupby("product")["price"].transform(
            lambda s: s.rolling(window=w, min_periods=1).mean()
        )
    result["volatility"] = result.groupby("product")["price"].transform(
        lambda s: s.rolling(window=7, min_periods=1).std()
    )
    result["pct_change"] = result.groupby("product")["price"].transform(
        lambda s: s.pct_change()
    )
    return result


def compute_region_stability(df: pd.DataFrame) -> float:
    """Compute region price stability coefficient.

    Lower values indicate more stable prices in that region.
    """
    product_stds = df.groupby("product")["price"].std()
    return float(product_stds.mean())
