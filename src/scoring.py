"""Explainable V2 apocalypse cost-effectiveness scoring model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


DEFAULT_WEIGHTS: dict[str, float] = {
    "attack": 0.35,
    "defense": 0.25,
    "production": 0.20,
    "control": 0.15,
    "special": 0.05,
}

SPECIAL_ABILITY_SCORES: dict[str, float] = {
    "SINGLE": 4.0,
    "PRODUCE": 9.0,
    "WALL": 8.0,
    "BOMB": 9.0,
    "SLOW": 8.0,
    "AOE": 10.0,
    "MULTI": 8.0,
    "SPLASH": 7.0,
    "SIGHT": 7.0,
}

MIN_EFFECTIVE_SUN_COST = 25.0

DIMENSION_LABELS = {
    "attack": "攻击",
    "defense": "防御",
    "production": "产能",
    "control": "控制",
    "special": "特殊能力",
}

SCORING_PLANT_COLUMNS = {
    "name",
    "vegetable_name",
    "sun_cost",
    "attack",
    "defense",
    "production",
    "control",
    "special_ability",
    "role",
}


def normalize_weights(weights: Mapping[str, float] | None = None) -> dict[str, float]:
    """Validate and normalize all five battle-value weights to sum to one."""

    supplied = dict(DEFAULT_WEIGHTS if weights is None else weights)
    missing = set(DEFAULT_WEIGHTS).difference(supplied)
    if missing:
        raise ValueError(f"评分权重缺少维度: {', '.join(sorted(missing))}")
    normalized_input = {
        key: float(supplied[key]) for key in DEFAULT_WEIGHTS
    }
    if any(value < 0 for value in normalized_input.values()):
        raise ValueError("评分权重不能为负数")
    total = sum(normalized_input.values())
    if total <= 0:
        raise ValueError("评分权重之和必须大于 0")
    return {key: value / total for key, value in normalized_input.items()}


def apply_weight_multipliers(
    multipliers: Mapping[str, float] | None = None,
    *,
    base_weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Create traceable scenario weights from the confirmed base weights."""

    base = normalize_weights(base_weights)
    factors = {key: 1.0 for key in DEFAULT_WEIGHTS}
    if multipliers:
        unknown = set(multipliers).difference(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"未知评分维度: {', '.join(sorted(unknown))}")
        factors.update({key: float(value) for key, value in multipliers.items()})
    if any(value < 0 for value in factors.values()):
        raise ValueError("场景权重倍率不能为负数")
    return normalize_weights({key: base[key] * factors[key] for key in base})


def calculate_apocalypse_scores(
    plants: pd.DataFrame,
    featured_prices: pd.DataFrame,
    *,
    weights: Mapping[str, float] | None = None,
    minimum_effective_sun_cost: float = MIN_EFFECTIVE_SUN_COST,
) -> pd.DataFrame:
    """Rank every plant with the confirmed apocalypse index formula.

    Attack damage is scaled to the same 0-10 range as defense, production,
    control, and special ability before applying weights.  The optimizer still
    consumes the original sun cost; the minimum cost only prevents free plants
    from dividing the model score by zero.
    """

    missing_plant_columns = SCORING_PLANT_COLUMNS.difference(plants.columns)
    if missing_plant_columns:
        raise ValueError(
            f"评分植物数据缺少字段: {', '.join(sorted(missing_plant_columns))}"
        )
    if plants.empty:
        raise ValueError("评分植物数据不能为空")
    if minimum_effective_sun_cost <= 0:
        raise ValueError("最低有效阳光成本必须大于 0")

    required_price_columns = {
        "date",
        "name",
        "price",
        "source",
        "historical_mean",
        "volatility",
    }
    missing = required_price_columns.difference(featured_prices.columns)
    if missing:
        raise ValueError(f"评分菜价缺少字段: {', '.join(sorted(missing))}")

    price_data = featured_prices.copy()
    price_data["date"] = pd.to_datetime(price_data["date"], errors="coerce")
    for column in ("price", "historical_mean", "volatility"):
        price_data[column] = pd.to_numeric(price_data[column], errors="coerce")
    price_data = price_data.dropna(
        subset=["date", "name", "price", "historical_mean", "volatility"]
    )
    latest = (
        price_data.sort_values(["name", "date"])
        .groupby("name", as_index=False, sort=False)
        .tail(1)
        .rename(
            columns={
                "name": "vegetable_name",
                "price": "current_price",
                "date": "price_date",
            }
        )
    )
    latest = latest[
        [
            "vegetable_name",
            "price_date",
            "current_price",
            "historical_mean",
            "volatility",
            "source",
        ]
    ]

    scored = plants.copy().merge(
        latest,
        on="vegetable_name",
        how="left",
        validate="many_to_one",
    )
    unmatched = scored.loc[scored["current_price"].isna(), "name"].tolist()
    if unmatched:
        raise ValueError(f"以下植物没有最新菜价: {', '.join(unmatched)}")
    if scored["current_price"].le(0).any():
        raise ValueError("当前菜价必须大于 0")

    attack = pd.to_numeric(scored["attack"], errors="coerce").fillna(0)
    maximum_attack = float(attack.max())
    scored["attack_score"] = 0.0 if maximum_attack <= 0 else attack / maximum_attack * 10
    scored["defense_score"] = pd.to_numeric(scored["defense"], errors="coerce")
    scored["production_score"] = pd.to_numeric(scored["production"], errors="coerce")
    scored["control_score"] = pd.to_numeric(scored["control"], errors="coerce")
    if "special_score" in scored.columns:
        special = pd.to_numeric(scored["special_score"], errors="coerce")
    else:
        tags = scored.get("special_tag", pd.Series("", index=scored.index))
        special = tags.astype(str).str.upper().map(SPECIAL_ABILITY_SCORES)
    scored["special_score"] = special.fillna(5.0)

    resolved_weights = normalize_weights(weights)
    component_columns = {
        "attack": "attack_score",
        "defense": "defense_score",
        "production": "production_score",
        "control": "control_score",
        "special": "special_score",
    }
    for dimension, score_column in component_columns.items():
        scored[f"{dimension}_contribution"] = (
            scored[score_column] * resolved_weights[dimension]
        )
    contribution_columns = [
        f"{dimension}_contribution" for dimension in DEFAULT_WEIGHTS
    ]
    scored["battle_value"] = scored[contribution_columns].sum(axis=1)
    scored["price_undervaluation"] = (
        scored["historical_mean"] / scored["current_price"]
    )
    scored["stability_coefficient"] = 1 / (1 + scored["volatility"].clip(lower=0))
    scored["effective_sun_cost"] = pd.to_numeric(
        scored["sun_cost"], errors="coerce"
    ).clip(lower=minimum_effective_sun_cost)
    scored["apocalypse_index"] = (
        scored["battle_value"]
        * scored["price_undervaluation"]
        * scored["stability_coefficient"]
        / scored["effective_sun_cost"]
    )
    scored["latest_price"] = scored["current_price"]
    scored["recommendation_reason"] = scored.apply(explain_score, axis=1)

    scored = scored.sort_values(
        ["apocalypse_index", "battle_value", "name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    scored["rank"] = scored.index + 1
    scored.attrs["weights"] = resolved_weights
    scored.attrs["minimum_effective_sun_cost"] = minimum_effective_sun_cost
    return scored


def explain_score(row: pd.Series | Mapping[str, Any]) -> str:
    """Generate a concise, component-based Chinese explanation for one score."""

    contributions = {
        dimension: float(row[f"{dimension}_contribution"])
        for dimension in DEFAULT_WEIGHTS
    }
    strongest = sorted(contributions, key=contributions.get, reverse=True)[:2]
    strengths = "、".join(DIMENSION_LABELS[item] for item in strongest)

    undervaluation = float(row["price_undervaluation"])
    if undervaluation >= 1.05:
        price_text = f"现价低于 30 日均值，低估系数 {undervaluation:.2f}"
    elif undervaluation <= 0.95:
        price_text = f"现价高于 30 日均值，低估系数 {undervaluation:.2f}"
    else:
        price_text = f"现价接近 30 日均值，低估系数 {undervaluation:.2f}"

    stability = float(row["stability_coefficient"])
    stability_text = "价格较稳定" if stability >= 0.90 else "价格波动需留意"
    sun_text = f"有效阳光成本 {float(row['effective_sun_cost']):g}"
    if float(row["sun_cost"]) < float(row["effective_sun_cost"]):
        sun_text += "（零/低费保护值）"
    return (
        f"主要优势是{strengths}；{price_text}；{stability_text}，"
        f"稳定系数 {stability:.2f}；{sun_text}。"
    )
