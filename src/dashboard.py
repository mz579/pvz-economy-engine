"""Data preparation helpers for the V2.0 Streamlit dashboard.

The UI currently uses the traceable offline CSV and the legacy utility score.
This keeps batch 6 runnable while the batch-2 pipeline and batch-4 apocalypse
index are still pending confirmation. The module deliberately exposes the score
source so the presentation layer cannot label it as the final V2 model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.optimizer import optimize_planting
from src.plant_mapping import load_plant_mapping
from src.valuator import adjust_weights_by_zombie_factor, calculate_utility


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FALLBACK_PRICE_PATH = PROJECT_ROOT / "data" / "fallback" / "vegetable_prices.csv"

ZOMBIE_MODES: dict[str, dict[str, Any]] = {
    "均衡巡逻": {
        "icon": "🧟",
        "description": "普通僵尸混合编队，攻防与特殊能力保持均衡。",
        "factors": {"swarm": 0.5, "tank": 0.3, "air": 0.2},
    },
    "尸潮来袭": {
        "icon": "🧟‍♂️",
        "description": "大量普通僵尸集中出现，范围能力和持续输出更重要。",
        "factors": {"swarm": 1.0, "tank": 0.2, "air": 0.1},
    },
    "铁桶强攻": {
        "icon": "🪣",
        "description": "高耐久目标推进，提高直接攻击能力的优先级。",
        "factors": {"swarm": 0.2, "tank": 1.0, "air": 0.1},
    },
    "迷雾夜战": {
        "icon": "🌫️",
        "description": "视野受限且敌情复杂，更重视特殊能力和控制。",
        "factors": {"swarm": 0.8, "tank": 0.4, "air": 0.8},
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


def load_offline_prices(path: Path | str = FALLBACK_PRICE_PATH) -> pd.DataFrame:
    """Load and validate the traceable local price sample."""

    prices = pd.read_csv(path)
    required = {"date", "product", "price"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"离线菜价缺少字段: {', '.join(sorted(missing))}")

    prices = prices.copy()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices["price"] = pd.to_numeric(prices["price"], errors="coerce")
    prices = prices.dropna(subset=["date", "product", "price"])
    prices["source"] = "local_csv_fallback"
    return prices.sort_values(["product", "date"]).reset_index(drop=True)


def build_dashboard_model(
    zombie_mode: str,
    available_sun: int,
    available_cells: int,
) -> dict[str, Any]:
    """Build the read-only view model consumed by the Streamlit page."""

    if zombie_mode not in ZOMBIE_MODES:
        raise ValueError(f"未知僵尸模式: {zombie_mode}")

    plants = load_plant_mapping()
    prices = load_offline_prices()
    mode = ZOMBIE_MODES[zombie_mode]
    weights = adjust_weights_by_zombie_factor(mode["factors"])
    utility = calculate_utility(plants, weights=weights)

    ranking = plants.merge(
        utility[["name", "raw_utility", "utility"]],
        on="name",
        validate="one_to_one",
    )
    latest_date = prices["date"].max()
    latest_prices = (
        prices.loc[prices["date"] == latest_date]
        .groupby("product", as_index=False)["price"]
        .mean()
        .rename(columns={"product": "vegetable_name", "price": "latest_price"})
    )
    ranking = ranking.merge(
        latest_prices, on="vegetable_name", how="left", validate="many_to_one"
    )
    ranking["utility"] = ranking["utility"].round(4)
    ranking["raw_utility"] = ranking["raw_utility"].round(4)
    ranking["latest_price"] = ranking["latest_price"].round(2)
    ranking = ranking.sort_values("utility", ascending=False).reset_index(drop=True)
    ranking["rank"] = ranking.index + 1

    result = optimize_planting(
        ranking,
        available_sun=available_sun,
        available_cells=available_cells,
        score_column="utility",
    )
    reasons = build_recommendation_reasons(
        result, ranking, prices, zombie_mode=zombie_mode
    )

    return {
        "zombie_mode": zombie_mode,
        "mode": mode,
        "weights": weights,
        "plants": plants,
        "prices": prices,
        "ranking": ranking,
        "result": result,
        "reasons": reasons,
        "latest_date": latest_date,
        "data_source": "本地离线 CSV fallback",
        "score_label": "兼容推荐指数",
        "score_notice": "第 4 批参数待确认，当前排名使用兼容战力 utility。",
    }


def get_price_trend(prices: pd.DataFrame, vegetable_name: str) -> pd.DataFrame:
    """Return a single vegetable's date/price series for charting."""

    return (
        prices.loc[prices["product"] == vegetable_name, ["date", "price"]]
        .sort_values("date")
        .reset_index(drop=True)
    )


def build_recommendation_reasons(
    result: dict[str, Any],
    ranking: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    zombie_mode: str,
) -> list[dict[str, Any]]:
    """Explain each selected plant without inventing the pending V2 formula."""

    indexed = ranking.set_index("name", drop=False)
    reasons: list[dict[str, Any]] = []
    for item in result["combination"]:
        row = indexed.loc[item["name"]]
        trend = get_price_trend(prices, row["vegetable_name"])
        current_price = float(trend.iloc[-1]["price"])
        recent_average = float(trend.tail(7)["price"].mean())
        if current_price < recent_average * 0.98:
            price_context = "低于近 7 日均价"
        elif current_price > recent_average * 1.02:
            price_context = "高于近 7 日均价"
        else:
            price_context = "接近近 7 日均价"

        reasons.append(
            {
                "name": item["name"],
                "emoji": PLANT_EMOJI.get(item["name"], "🌱"),
                "quantity": item["quantity"],
                "role": row["role"],
                "ability": row["special_ability"],
                "score": float(row["utility"]),
                "vegetable_name": row["vegetable_name"],
                "current_price": round(current_price, 2),
                "recent_average": round(recent_average, 2),
                "text": (
                    f"在“{zombie_mode}”中承担{row['role']}；{row['special_ability']}。"
                    f"单株兼容指数 {row['utility']:.2f}，阳光成本 {row['sun_cost']}。"
                    f"映射蔬菜{row['vegetable_name']}最新价 {current_price:.2f} 元/kg，"
                    f"{price_context}。"
                ),
            }
        )
    return reasons
