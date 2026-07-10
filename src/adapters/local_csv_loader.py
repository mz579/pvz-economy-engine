
"""本地 CSV 文件加载适配器.

作为网络爬虫的 Fallback 兜底方案，读取 data/fallback/ 目录下预置的 CSV 文件。
也支持用户上传自定义 CSV 文件。
"""

import os
from typing import Optional, List

import pandas as pd

from src.adapters.base_spider import BaseSpider


class LocalCSVLoader(BaseSpider):
    """本地/离线 CSV 文件加载器."""

    def __init__(self):
        """初始化 CSV 加载器."""
        super().__init__(
            source_name="local_csv",
            display_name="本地 CSV 文件加载器",
            data_dir="data/fallback/",
        )

    def fetch(
        self, filepath: Optional[str] = None, **kwargs
    ) -> Optional[List[dict]]:
        """从指定 CSV 文件读取原始数据.

        Args:
            filepath: CSV 文件路径。为 None 时自动读取 data_dir 下最新的 .csv 文件。
            **kwargs: 预留扩展参数。

        Returns:
            字典列表，或 None (读取失败时)。
        """
        if filepath is None:
            filepath = self._find_latest_csv()
            if filepath is None:
                print("[local_csv] 未找到可用的 CSV 文件")
                return None

        try:
            df = pd.read_csv(filepath)
            print(f"[local_csv] 成功加载 {len(df)} 条记录: {filepath}")
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"[local_csv] 读取 CSV 失败: {e}")
            return None

    def parse(self, raw_data: List[dict]) -> pd.DataFrame:
        """将 CSV 原始数据解析为标准格式.

        自动检测输入列名，兼容以下两种命名风格:
          - [date, product, price, source]  (标准)
          - [日期, 品种, 价格, 数据来源]     (中文)

        Args:
            raw_data: fetch() 返回的字典列表。

        Returns:
            标准化 DataFrame，列: [date, product, price, source]。
        """
        if not raw_data:
            return pd.DataFrame(columns=["date", "product", "price", "source"])

        df = pd.DataFrame(raw_data)

        # 兼容中英文列名
        column_map = {
            "日期": "date",
            "品种": "product",
            "蔬菜": "product",
            "价格": "price",
            "均价": "price",
            "数据来源": "source",
        }
        df.rename(columns=column_map, inplace=True)

        # 确保标准列存在
        for col in ["date", "product", "price"]:
            if col not in df.columns:
                raise ValueError(f"CSV 缺少必要列: {col}")

        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.dropna(subset=["date", "price"], inplace=True)

        if "source" not in df.columns:
            df["source"] = self.source_name

        return df[["date", "product", "price", "source"]].reset_index(drop=True)

    def _find_latest_csv(self) -> Optional[str]:
        """在 data_dir 中查找最新的 .csv 文件.

        Returns:
            最新 CSV 文件的完整路径，或 None。
        """
        if not os.path.isdir(self.data_dir):
            return None
        csv_files = [
            os.path.join(self.data_dir, f)
            for f in os.listdir(self.data_dir)
            if f.endswith(".csv")
        ]
        if not csv_files:
            return None
        return max(csv_files, key=os.path.getmtime)
