"""Guangzhou Jiangnan fruit & vegetable market spider adapter.

Data source: Guangzhou Jiangnan fruit and vegetable market (public data).
Falls back to local CSV when scraping fails.
"""
import random
from typing import Optional, List
import pandas as pd
import requests
from src.adapters.base_spider import BaseSpider
from src.config import REQUEST_TIMEOUT


class GuangzhouSpider(BaseSpider):
    """Guangzhou Jiangnan fruit & vegetable market spider adapter."""

    def __init__(self):
        super().__init__(
            source_name="guangzhou",
            display_name=chr(24191) + chr(24030) + chr(27743) + chr(21335) + chr(26524) + chr(33756) + chr(24066) + chr(22330),
            data_dir="data/guangzhou/",
        )
        self.session = requests.Session()

    def fetch(self) -> Optional[List[dict]]:
        try:
            return self._fetch_api()
        except Exception:
            return self._fetch_fallback()

    def _fetch_api(self) -> Optional[List[dict]]:
        headers = {"User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        ])}
        resp = self.session.get(
            "http://www.gzjnmarket.com/api/v1/price/list",
            headers=headers, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        records = []
        for item in data.get("data", []):
            records.append({
                "date": item.get("date"),
                "product": item.get("name"),
                "price": float(item.get("price", 0)),
            })
        return records

    def parse(self, raw_data: List[dict]) -> Optional[pd.DataFrame]:
        if not raw_data:
            return None
        df = pd.DataFrame(raw_data)
        df["date"] = pd.to_datetime(df["date"])
        df["price"] = df["price"].astype(float)
        df = df.dropna(subset=["date", "product", "price"])
        df = df.sort_values(["product", "date"]).reset_index(drop=True)
        return df

    def _fetch_fallback(self) -> Optional[List[dict]]:
        import os
        csv_path = os.path.join(self.data_dir, "guangzhou_prices.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            return df.to_dict(orient="records")
        return None
