
"数据标准化清洗与特征工程模块.

负责将不同适配器输出的数据统一为标准时序格式，
包含跨地区品种别名映射、缺失值插值、异常值剔除，
以及时间序列特征工程。
"

from typing import Dict, List, Optional

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# 跨地区品种别名映射表
# ---------------------------------------------------------------------------
# key: 标准品种名称 (用于下游建模)
# value: 各地区可能出现的别名列表

PRODUCT_ALIAS: Dict[str, List[str]] = {
    "豌豆": ["豌豆", "青豌豆", "荷兰豆"],
    "樱桃": ["樱桃", "车厘子", "樱珠"],
    "生菜": ["生菜", "叶用莴苣", "团生菜"],
    "油菜": ["油菜", "小白菜", "青菜", "上海青"],
    "大蒜": ["大蒜", "蒜头", "大蒜(蒜头)"],

    "??": ["??", "???", "???"],
    "??": ["??", "???", "??"],
    "??": ["??", "????", "???"],

    "大白菜": ["白菜", "大白菜", "黄芽白", "结球白菜"],
    "土豆": ["马铃薯", "洋芋", "土豆", "马铃薯(土豆)"],
    "西红柿": ["番茄", "西红柿", "番茄(西红柿)", "蕃茄"],
    "黄瓜": ["黄瓜", "青瓜", "胡瓜"],
    "茄子": ["茄子", "落苏", "昆仑瓜"],
    "青椒": ["青椒", "甜椒", "灯笼椒", "菜椒", "柿子椒"],
    "豆角": ["豆角", "四季豆", "菜豆", "芸豆", "扁豆"],
    "菠菜": ["菠菜", "波斯菜", "赤根菜"],
    "胡萝卜": ["胡萝卜", "红萝卜", "甘荀"],
    "芹菜": ["芹菜", "旱芹", "药芹", "香芹"],
    "韭菜": ["韭菜", "韭", "起阳草"],
    "洋葱": ["洋葱", "葱头", "圆葱", "洋蒜"],
    "大蒜": ["大蒜", "蒜头", "大蒜(蒜头)"],
    "生菜": ["生菜", "叶用莴苣"],
    "油菜": ["油菜", "小白菜", "青菜", "上海青"],
}

# ---------------------------------------------------------------------------
# 标准化清洗
# ---------------------------------------------------------------------------


def standardize_price_data(
    df: pd.DataFrame, source_name: Optional[str] = None
) -> pd.DataFrame:
    "将任意适配器的原始数据统一为标准时序格式.

    标准化输出列: [date, product, price, source]
    同时应用品种别名映射、缺失值插值和异常值剔除。

    Args:
        df: 输入 DataFrame，需包含 date, product, price 列。
        source_name: 数据来源标记，为 None 时保留 df 中的 source 列。

    Returns:
        标准化后的 Pandas DataFrame。
    "
    if df.empty:
        return pd.DataFrame(columns=["date", "product", "price", "source"])

    result = df.copy()

    # 1. 统一品种名称 (别名 → 标准名)
    result["product"] = result["product"].apply(_map_product_alias)

    # 2. 设置来源标记
    if source_name:
        result["source"] = source_name

    # 3. 按品种分别插值 (线性填充缺失日期)
    result = result.sort_values(["product", "date"]).reset_index(drop=True)
    result["price"] = result.groupby("product")["price"].transform(
        lambda s: s.interpolate(method="linear").bfill().ffill()
    )

    # 4. 异常值剔除 (3σ 原则)
    result = _remove_outliers(result)

    # 5. 确保日期列为 datetime
    result["date"] = pd.to_datetime(result["date"])

    # 6. 只保留必要列
    cols = [c for c in ["date", "product", "price", "source"] if c in result.columns]
    return result[cols].reset_index(drop=True)


def _map_product_alias(name: str) -> str:
    "将别名映射为标准品种名称.

    Args:
        name: 原始品种名称。

    Returns:
        标准品种名称，若未匹配则返回原值。
    "
    if not isinstance(name, str):
        return str(name)
    name = name.strip()
    for standard, aliases in PRODUCT_ALIAS.items():
        if name == standard or name in aliases:
            return standard
    return name


def _remove_outliers(
    df: pd.DataFrame, col: str = "price", sigma: float = 3.0
) -> pd.DataFrame:
    "剔除指定列中的异常值 (3σ 原则).

    Args:
        df: 输入 DataFrame。
        col: 需要检查的列名，默认为 "price"。
        sigma: 标准差倍数阈值，默认 3.0。

    Returns:
        剔除异常值后的 DataFrame。
    "
    mean = df[col].mean()
    std = df[col].std()
    lower = mean - sigma * std
    upper = mean + sigma * std
    mask = (df[col] >= lower) & (df[col] <= upper)
    removed = (~mask).sum()
    if removed > 0:
        print(f"[preprocess] 剔除 {removed} 个异常值 ({col} 超出 {sigma}σ)")
    return df[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    "生成时间序列特征.

    包括:
        - price_ma7:  7 日移动平均
        - price_ma14: 14 日移动平均
        - price_ma30: 30 日移动平均
        - volatility: 7 日波动率 (标准差)
        - pct_change: 日环比涨跌幅

    Args:
        df: 标准化后的 DataFrame (需包含 date, product, price 列)。

    Returns:
        追加特征列后的 DataFrame。
    "
    result = df.copy()

    # 按品种分组计算特征
    result = result.sort_values(["product", "date"]).reset_index(drop=True)

    windows = [7, 14, 30]
    for w in windows:
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
    "计算地区价格稳定系数.

    基于全品种历史价格的标准差均值，数值越小表示该地区价格越稳定。

    Args:
        df: 标准化后的 DataFrame。

    Returns:
        地区稳定系数 (所有品种标准差均值)。
    "
    product_stds = df.groupby("product")["price"].std()
    return float(product_stds.mean())
