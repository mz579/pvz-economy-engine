
"""北京新发地批发市场数据爬虫适配器.

数据来源: 北京新发地官网公开日度蔬菜价格。
遇到反爬或网络异常时，自动降级到 LocalCSVLoader 从本地 fallback 读取。
"""

import time
import random
from typing import Optional, List

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.adapters.base_spider import BaseSpider
from src.config import REQUEST_TIMEOUT, USER_AGENTS


class XinfadiSpider(BaseSpider):
    """北京新发地批发市场爬虫适配器."""

    BASE_URL = "http://www.xinfadi.com.cn/priceDetail.html"

    def __init__(self):
        """初始化新发地爬虫."""
        super().__init__(
            source_name="xinfadi",
            display_name="北京新发地批发市场",
            data_dir="data/beijing/",
        )
        self.session = requests.Session()

    def _get_headers(self) -> dict:
        """从 User-Agent 池中随机选取一个请求头.

        Returns:
            请求头字典。
        """
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def fetch(self, page: int = 1, **kwargs) -> Optional[List[dict]]:
        """从新发地官网拉取价格数据.

        Args:
            page: 页码，默认第1页。
            **kwargs: 预留扩展参数。

        Returns:
            原始记录列表，或 None (请求失败时)。
        """
        try:
            resp = self.session.get(
                self.BASE_URL,
                headers=self._get_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except requests.RequestException as e:
            print(f"[xinfadi] HTTP 请求失败: {e}，将降级到本地 CSV 加载器")
            return None

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = []
            table = soup.find("table", class_="price-table")
            if table is None:
                print("[xinfadi] 未找到价格表格，返回空数据")
                return rows

            for tr in table.find_all("tr")[1:]:  # 跳过表头
                cols = tr.find_all("td")
                if len(cols) >= 3:
                    record = {
                        "date": cols[0].get_text(strip=True),
                        "product": cols[1].get_text(strip=True),
                        "price": cols[2].get_text(strip=True),
                    }
                    rows.append(record)

            # 添加随机延时，避免请求过于频繁
            time.sleep(random.uniform(0.5, 1.5))
            return rows

        except Exception as e:
            print(f"[xinfadi] 解析 HTML 失败: {e}")
            return None

    def parse(self, raw_data: List[dict]) -> pd.DataFrame:
        """将新发地原始数据解析为标准格式.

        Args:
            raw_data: fetch() 返回的原始记录列表。

        Returns:
            标准化 DataFrame，列: [date, product, price, source]。
        """
        if not raw_data:
            return pd.DataFrame(columns=["date", "product", "price", "source"])

        df = pd.DataFrame(raw_data)
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.dropna(subset=["date", "price"], inplace=True)
        df["source"] = self.source_name
        return df[["date", "product", "price", "source"]].reset_index(drop=True)
