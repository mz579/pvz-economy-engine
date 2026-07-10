
"""相对估值模块 — 锚定基准 + 多因子加权估值模型.

核心逻辑：
1. 定基准 (Base Anchor): 以"豌豆射手"为锚，定义其综合效用指数 = 1.0。
2. 建权 (Utility Score, U): 多因子加权计算每个植物的综合战力指数。
3. 算偏离 (Deviation): 理论基准价与实际市场价的偏离度，识别低估/高估品种。
"""

from typing import Dict, Optional

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# 特殊标签量化系数
# ---------------------------------------------------------------------------

SPECIAL_MULTIPLIER: Dict[str, float] = {
    "AOE": 1.5,      # 群体伤害
    "SPLASH": 1.3,   # 溅射伤害
    "MULTI": 1.4,    # 多行攻击
    "SLOW": 1.2,     # 减速效果
    "BOMB": 1.6,     # 一次性高伤
    "SINGLE": 1.0,   # 单体攻击
    "WALL": 0.8,     # 防御（硬性减伤，效用系数偏低）
    "PRODUCE": 1.2,  # 阳光生产
    "SIGHT": 0.7,    # 视野辅助
}

# 默认因子权重 (可根据僵尸威胁风格动态调整)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "attack": 0.5,
    "hp": 0.3,
    "special": 0.2,
}

# ---------------------------------------------------------------------------
# 综合战力指数 (Utility Score)
# ---------------------------------------------------------------------------


def calculate_utility(
    df_plants: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    special_multiplier: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """计算每个植物的综合战力指数 U.

    公式:
        U = w_attack * (attack / max_attack)
          + w_hp * (hp / max_hp)
          + w_special * special_factor

    并以"豌豆射手"为基准进行归一化，使其 U_peashooter = 1.0。

    Args:
        df_plants: 植物参数表，需包含 name, attack, hp, special_tag 列。
        weights: 因子权重字典，默认为 DEFAULT_WEIGHTS。
        special_multiplier: 特殊标签映射字典，默认为 SPECIAL_MULTIPLIER。

    Returns:
        追加了 raw_utility 和 utility (归一化后) 列的 DataFrame。
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS.copy()
    if special_multiplier is None:
        special_multiplier = SPECIAL_MULTIPLIER.copy()

    result = df_plants.copy()

    # 极差归一化攻击力和生命值
    max_attack = result["attack"].max()
    max_hp = result["hp"].max()
    norm_attack = result["attack"] / max_attack if max_attack > 0 else 0
    norm_hp = result["hp"] / max_hp if max_hp > 0 else 0

    # 特殊标签量化系数
    special_factor = result["special_tag"].map(
        lambda t: special_multiplier.get(t, 1.0)
    )

    # 计算原始综合战力指数
    result["raw_utility"] = (
        weights["attack"] * norm_attack
        + weights["hp"] * norm_hp
        + weights["special"] * special_factor
    )

    # 以豌豆射手为锚归一化
    peashooter_utility = result.loc[
        result["name"] == "豌豆射手", "raw_utility"
    ].values
    if len(peashooter_utility) > 0 and peashooter_utility[0] > 0:
        result["utility"] = result["raw_utility"] / peashooter_utility[0]
    else:
        result["utility"] = result["raw_utility"]

    return result


# ---------------------------------------------------------------------------
# 相对估值偏离度 (Deviation)
# ---------------------------------------------------------------------------


def calc_deviation(
    price_df: pd.DataFrame,
    utility_df: pd.DataFrame,
    plant_price_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """计算每个植物的相对估值偏离度.

    映射逻辑：
        蔬菜品种 → 游戏植物 (通过 plant_price_map 建立映射关系)

    核心公式：
        理论基准价 = 基准价格 × (该植物U / 基准植物U)
        偏离度 = (实际市场价 / 理论基准价) - 1

    Args:
        price_df: 标准化菜价 DataFrame，需包含 product, price 列
                   (通常取最近日期的价格快照)。
        utility_df: 包含 utility 列的植物效用 DataFrame。
        plant_price_map: 植物→蔬菜品种的映射字典。
                    例如 {"豌豆射手": "豌豆"}。
                    默认使用内置的近似映射。

    Returns:
        包含 plant, market_price, 理论基准价, deviation, signal 的 DataFrame。
    """
    if plant_price_map is None:
        plant_price_map = _default_plant_price_map()

    # 获取最近一期的市场价格快照
    price_snapshot = _get_latest_prices(price_df)

    # 构建映射结果
    records = []
    for _, plant_row in utility_df.iterrows():
        plant_name = plant_row["name"]
        utility = plant_row["utility"]

        # 查找对应的蔬菜品种
        if plant_name not in plant_price_map:
            continue
        veggie = plant_price_map[plant_name]

        # 查找市场价格（可能存在多个匹配，取均值）
        market_rows = price_snapshot[
            price_snapshot["product"].str.contains(veggie, na=False)
        ]
        if market_rows.empty:
            continue
        market_price = market_rows["price"].mean()

        records.append(
            {
                "plant": plant_name,
                "utility": utility,
                "market_price": round(market_price, 3),
            }
        )

    result = pd.DataFrame(records)
    if result.empty:
        return result

    # 以豌豆射手为基准计算理论价格
    base_row = result[result["plant"] == "豌豆射手"]
    if base_row.empty:
        return result

    base_price = base_row["market_price"].values[0]
    base_utility = base_row["utility"].values[0]

    # 理论基准价 = 基准价格 × (该植物U / 基准植物U)
    result["理论基准价"] = base_price * (result["utility"] / base_utility)
    result["deviation"] = (result["market_price"] / result["理论基准价"]) - 1
    result["signal"] = result["deviation"].apply(
        lambda d: "低估" if d < 0 else "高估"
    )

    return result.sort_values("deviation", ascending=True).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _default_plant_price_map() -> Dict[str, str]:
    """建立植物名称 → 蔬菜品种的默认映射.

    Returns:
        映射字典 {植物名: 蔬菜品种关键词}.
    """
    return {
        "豌豆射手": "豌豆",
        "向日葵": "油菜",
        "坚果墙": "大白菜",
        "土豆雷": "土豆",
        "寒冰射手": "黄瓜",
        "双发射手": "豌豆",
        "樱桃炸弹": "樱桃",
        "大嘴花": "生菜",
        "食人花": "菠菜",
        "三线射手": "豌豆",
        "高坚果": "大白菜",
        "小喷菇": "大蒜",
        "阳光菇": "油菜",
        "大喷菇": "大蒜",
        "灯笼草": "芹菜",
    }


def _get_latest_prices(df: pd.DataFrame) -> pd.DataFrame:
    """从价格时间序列表中提取最新日期的价格快照.

    Args:
        df: 标准化的价格 DataFrame (含 date, product, price)。

    Returns:
        每个产品最新价格快照的 DataFrame。
    """
    latest_date = df["date"].max()
    snapshot = df[df["date"] == latest_date].copy()
    # 同一产品取均值
    snapshot = snapshot.groupby("product")["price"].mean().reset_index()
    return snapshot


def adjust_weights_by_zombie_factor(
    zombie_factor: Dict[str, float],
) -> Dict[str, float]:
    """根据僵尸威胁因子动态调整估值权重.

    僵尸威胁因子:
        swarm: 群体僵尸权重 → 提高 special (AOE 需求)
        tank: 重装僵尸权重 → 提高 attack (高伤害需求)
        air: 空军僵尸权重 → 提高 special (特定克制需求)

    Args:
        zombie_factor: 僵尸因子字典 {swarm: 0-1, tank: 0-1, air: 0-1}。

    Returns:
        调整后的权重字典。
    """
    base = DEFAULT_WEIGHTS.copy()
    # 群体威胁提升 special 权重
    special_bonus = zombie_factor.get("swarm", 0.5) * 0.15
    # 重装威胁提升 attack 权重
    attack_bonus = zombie_factor.get("tank", 0.3) * 0.15
    # 空军权重从 attack 和 hp 中均衡扣除
    deduction = (special_bonus + attack_bonus) / 2

    base["attack"] = min(base["attack"] + attack_bonus - deduction, 0.7)
    base["hp"] = max(base["hp"] - deduction, 0.1)
    base["special"] = min(base["special"] + special_bonus - deduction, 0.5)

    # 归一化确保和为 1
    total = sum(base.values())
    for k in base:
        base[k] = round(base[k] / total, 4)

    return base
