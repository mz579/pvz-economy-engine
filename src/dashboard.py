"""View-model assembly for the V2.0 Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.optimizer import optimize_planting
from src.pipeline import DEFAULT_PROCESSED_PATH, load_or_build_processed_prices
from src.plant_mapping import load_plant_mapping
from src.preprocess import NORMALIZED_PRICE_UNIT
from src.scoring import apply_weight_multipliers, calculate_apocalypse_scores


ZOMBIE_MODES: dict[str, dict[str, Any]] = {
    "均衡巡逻": {
        "icon": "🧟",
        "description": "普通僵尸混合编队，攻防、产能与控制保持基础权重。",
        "weight_multipliers": {},
    },
    "尸潮来袭": {
        "icon": "🧟‍♂️",
        "description": "大量普通僵尸集中出现，提高控制与范围特殊能力权重。",
        "weight_multipliers": {"attack": 1.05, "defense": 0.85, "production": 0.9, "control": 1.25, "special": 1.3},
    },
    "铁桶强攻": {
        "icon": "🪣",
        "description": "高耐久目标推进，提高直接攻击与防御的权重。",
        "weight_multipliers": {"attack": 1.25, "defense": 1.15, "production": 0.9, "control": 0.85, "special": 0.8},
    },
    "迷雾夜战": {
        "icon": "🌫️",
        "description": "视野受限且敌情复杂，提高控制与特殊能力权重。",
        "weight_multipliers": {"attack": 0.9, "defense": 0.9, "production": 0.9, "control": 1.25, "special": 1.5},
    },
}

PLANT_EMOJI = {
    "豌豆射手": "🫛",
    "向日葵": "🌻",
    "坚果墙": "🥜",
    "土豆雷": "🥔",
    "寒冰射手": "🧊",
    "双发射手": "🌱",
    "樱桃炸弹": "🍒",
    "大嘴花": "🌺",
    "食人花": "🪴",
    "三线射手": "🌿",
    "高坚果": "🛡️",
    "小喷菇": "🍄",
    "阳光菇": "🌤️",
    "大喷菇": "🟣",
    "灯笼草": "🏮",
}


def load_offline_prices(
    path: Path | str = DEFAULT_PROCESSED_PATH,
) -> pd.DataFrame:
    """Load or generate the processed offline price features."""

    return load_or_build_processed_prices(path, prefer_network=False)


def build_dashboard_model(
    zombie_mode: str,
    available_sun: int,
    available_cells: int,
    *,
    processed_path: Path | str = DEFAULT_PROCESSED_PATH,
    price_data: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Build the explainable, optimizer-ready model consumed by Streamlit."""

    if zombie_mode not in ZOMBIE_MODES:
        raise ValueError(f"未知僵尸模式: {zombie_mode}")

    all_plants = load_plant_mapping()
    prices = (
        load_offline_prices(processed_path)
        if price_data is None
        else _validate_featured_prices(price_data)
    )
    available_vegetables = set(prices["name"].dropna().astype(str).str.strip())
    plants = all_plants.loc[
        all_plants["vegetable_name"].isin(available_vegetables)
    ].copy()
    if plants.empty:
        expected = "、".join(sorted(all_plants["vegetable_name"].unique()))
        raise ValueError(f"上传菜名无法关联任何植物，可用标准菜名包括：{expected}")
    excluded_plants = all_plants.loc[
        ~all_plants["name"].isin(plants["name"]), "name"
    ].tolist()
    mode = ZOMBIE_MODES[zombie_mode]
    weights = apply_weight_multipliers(mode["weight_multipliers"])
    ranking = calculate_apocalypse_scores(plants, prices, weights=weights)

    result = optimize_planting(
        ranking,
        available_sun=available_sun,
        available_cells=available_cells,
        score_column="apocalypse_index",
    )
    reasons = build_recommendation_reasons(
        result, ranking, zombie_mode=zombie_mode
    )
    latest_date = pd.to_datetime(prices["date"]).max()
    sources = sorted(prices["source"].dropna().astype(str).unique())
    source_labels = {
        "local_csv_fallback": "本地离线 CSV fallback",
        "xinfadi_official": "北京新发地公开价格",
    }
    data_source = "、".join(_source_label(item, source_labels) for item in sources)
    price_unit = str(prices.attrs.get("price_unit", NORMALIZED_PRICE_UNIT))
    candidate_comparison = build_candidate_comparison(
        all_plants,
        ranking,
        result,
        price_unit=price_unit,
    )
    max_plant_share = float(result["max_plant_share"])
    per_plant_limit = int(result["per_plant_limit"])

    return {
        "zombie_mode": zombie_mode,
        "mode": mode,
        "weights": weights,
        "plants": plants,
        "all_plants": all_plants,
        "prices": prices,
        "ranking": ranking,
        "result": result,
        "reasons": reasons,
        "latest_date": latest_date,
        "data_source": data_source,
        "data_mode": _data_mode_label(sources),
        "price_unit": price_unit,
        "candidate_comparison": candidate_comparison,
        "score_label": "末日性价比指数",
        "score_notice": "战斗价值 × 价格低估系数 × 稳定性系数 ÷ 有效阳光成本",
        "concentration_policy": {
            "max_plant_share": max_plant_share,
            "per_plant_limit": per_plant_limit,
            "description": (
                f"每种植物最多占草坪容量的 {max_plant_share:.0%}，"
                f"本轮最多 {per_plant_limit} 株。"
            ),
            "is_v2_assumption": True,
            "unused_cells": int(result["unused_cells"]),
            "unused_cells_reason": result["unused_cells_reason"],
        },
        "coverage": {
            "matched_plants": int(len(plants)),
            "total_plants": int(len(all_plants)),
            "uploaded_vegetables": int(prices["name"].nunique()),
            "matched_vegetables": int(plants["vegetable_name"].nunique()),
            "excluded_plants": excluded_plants,
        },
    }


def _validate_featured_prices(prices: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "name",
        "price",
        "source",
        "historical_mean",
        "volatility",
    }
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"地区菜价缺少处理后字段: {', '.join(sorted(missing))}")
    result = prices.copy()
    result.attrs["price_unit"] = prices.attrs.get(
        "price_unit", NORMALIZED_PRICE_UNIT
    )
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    if result["date"].isna().all():
        raise ValueError("地区菜价没有有效日期")
    return result


def _source_label(source: str, labels: dict[str, str]) -> str:
    if source.startswith("user_upload:"):
        return f"用户上传 · {source.split(':', 1)[1]}"
    return labels.get(source, source)


def _data_mode_label(sources: list[str]) -> str:
    if any(source.startswith("user_upload:") for source in sources):
        return "用户 CSV"
    if any(source == "local_csv_fallback" for source in sources):
        return "离线 fallback"
    return "在线数据"


def build_candidate_comparison(
    all_plants: pd.DataFrame,
    ranking: pd.DataFrame,
    result: dict[str, Any],
    *,
    price_unit: str,
) -> pd.DataFrame:
    """Return every plant with truthful mapped-price and selection metadata."""

    score_columns = [
        "name",
        "price_date",
        "current_price",
        "historical_mean",
        "apocalypse_index",
        "rank",
    ]
    comparison = all_plants.merge(
        ranking[score_columns],
        on="name",
        how="left",
        validate="one_to_one",
    )
    quantities = {
        item["name"]: int(item["quantity"])
        for item in result["combination"]
    }
    comparison["selected_quantity"] = (
        comparison["name"].map(quantities).fillna(0).astype(int)
    )
    comparison["selected"] = comparison["selected_quantity"].gt(0)
    comparison["has_price"] = comparison["current_price"].notna()
    comparison["price_unit"] = comparison["has_price"].map(
        {True: price_unit, False: None}
    )
    comparison["price_difference"] = (
        comparison["current_price"] - comparison["historical_mean"]
    )
    return comparison.sort_values(
        ["apocalypse_index", "name"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)


def get_price_trend(prices: pd.DataFrame, vegetable_name: str) -> pd.DataFrame:
    """Return one vegetable's ordered date/price series for charting."""

    return (
        prices.loc[prices["name"] == vegetable_name, ["date", "price"]]
        .sort_values("date")
        .reset_index(drop=True)
    )


def build_recommendation_reasons(
    result: dict[str, Any],
    ranking: pd.DataFrame,
    *,
    zombie_mode: str,
) -> list[dict[str, Any]]:
    """Explain each selected plant through visible scoring components."""

    indexed = ranking.set_index("name", drop=False)
    reasons: list[dict[str, Any]] = []
    for item in result["combination"]:
        row = indexed.loc[item["name"]]
        reasons.append(
            {
                "name": item["name"],
                "emoji": PLANT_EMOJI.get(item["name"], "🌱"),
                "quantity": item["quantity"],
                "role": row["role"],
                "ability": row["special_ability"],
                "score": float(row["apocalypse_index"]),
                "vegetable_name": row["vegetable_name"],
                "current_price": round(float(row["current_price"]), 2),
                "recent_average": round(float(row["historical_mean"]), 2),
                "text": (
                    f"在“{zombie_mode}”中承担{row['role']}，{row['special_ability']}。"
                    f"{row['recommendation_reason']}"
                    f"最终指数 {row['apocalypse_index']:.4f}，本组合种植 {item['quantity']} 株。"
                ),
            }
        )
    return reasons
