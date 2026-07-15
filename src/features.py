"""Price feature engineering kept separate from collection and cleaning."""

from __future__ import annotations

import pandas as pd

from src.preprocess import NORMALIZED_PRICE_UNIT, STANDARD_COLUMNS


FEATURE_COLUMNS = (
    "price_ma7",
    "price_ma14",
    "price_ma30",
    "historical_mean",
    "change_rate",
    "volatility",
    "price_rank",
)


def add_price_features(data: pd.DataFrame, *, history_window: int = 30) -> pd.DataFrame:
    """Add deterministic rolling features to cleaned price records.

    Volatility is the 30-day coefficient of variation (standard deviation / mean),
    matching the confirmed scoring definition.  ``min_periods=1`` keeps the
    offline pipeline usable for short user-supplied histories.
    """

    if history_window < 1:
        raise ValueError("history_window 必须大于 0")
    missing = set(STANDARD_COLUMNS).difference(data.columns)
    if missing:
        raise ValueError(f"特征输入缺少字段: {', '.join(sorted(missing))}")
    if data.empty:
        result = data.assign(
            **{column: pd.Series(dtype=float) for column in FEATURE_COLUMNS}
        )
        result.attrs["price_unit"] = data.attrs.get(
            "price_unit", NORMALIZED_PRICE_UNIT
        )
        return result

    result = data.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.sort_values(["name", "date"]).reset_index(drop=True)
    grouped = result.groupby("name", sort=False)["price"]

    for window in (7, 14, 30):
        result[f"price_ma{window}"] = grouped.transform(
            lambda series, size=window: series.rolling(size, min_periods=1).mean()
        )

    result["historical_mean"] = grouped.transform(
        lambda series: series.rolling(history_window, min_periods=1).mean()
    )
    rolling_std = grouped.transform(
        lambda series: series.rolling(history_window, min_periods=1).std(ddof=0)
    )
    result["volatility"] = rolling_std.div(result["historical_mean"]).fillna(0)
    result["change_rate"] = grouped.pct_change(fill_method=None).fillna(0)
    result["price_rank"] = grouped.rank(method="average", pct=True)

    numeric_columns = [*FEATURE_COLUMNS]
    result[numeric_columns] = result[numeric_columns].replace(
        [float("inf"), float("-inf")], 0
    )
    result.attrs["price_unit"] = data.attrs.get("price_unit", NORMALIZED_PRICE_UNIT)
    return result
