"""Shandong Shouguang vegetable price index spider adapter.

Data source: Shouguang vegetable price index (public API).
Falls back to local CSV when scraping fails.
"""
import random
import json
from typing import Optional, List
import pandas as pd
import requests
from src.adapters.base_spider import BaseSpider
from src.config import REQUEST_TIMEOUT


class ShouguangSpider(BaseSpider):
    """Shandong Shouguang vegetable price index spider adapter."""

    def __init__(self):
        super().__init__(
            source_name="shouguang",
            display_name=chr(23665) + chr(19996) + chr(20852) + chr(20809) + chr(33756) + chr(33756) + chr(20215) + chr(26684) + chr(25351) + chr(25968),
            data_dir="data/shouguang/",
        )
        self.session = requests.Session()

    def fetch(self) -> Optional[List[dict]]:
        """Try to fetch from API, fall back to local CSV."""
        try:
            return self._fetch_api()
        except Exception as e:
            return self._fetch_fallback()

    def _fetch_api(self) -> Optional[List[dict]]:
        headers = {"User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        ])}
        # Shouguang index API endpoint
        resp = self.session.get(
            "http://www.sgvindex.com/api/v1/price/list",
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
        """Parse raw data into standardized DataFrame."""
        if not raw_data:
            return None
        df = pd.DataFrame(raw_data)
        df["date"] = pd.to_datetime(df["date"])
        df["price"] = df["price"].astype(float)
        df = df.dropna(subset=["date", "product", "price"])
        df = df.sort_values(["product", "date"]).reset_index(drop=True)
        return df

    def _fetch_fallback(self) -> Optional[List[dict]]:
        """Fall back to local CSV data."""
        import os
        csv_path = os.path.join(self.data_dir, "shouguang_prices.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            return df.to_dict(orient="records")
        return None
