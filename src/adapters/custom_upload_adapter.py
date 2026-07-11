"""Custom upload adapter for user-imported Excel/CSV data.

Allows advanced users to upload their own price data files
for any region/vegetable market.
"""
import os
from typing import Optional, List
import pandas as pd
from src.adapters.base_spider import BaseSpider


class CustomUploadAdapter(BaseSpider):
    """Load uploaded Excel/CSV files as price data source."""

    def __init__(self, file_path: str = ""):
        super().__init__(
            source_name="custom_upload",
            display_name=chr(19978) + chr(20256) + chr(19978) + chr(20256) + chr(25968) + chr(25454) + chr(20837) + chr(20837) + chr(20256) + chr(25454),  # User upload
            data_dir="data/custom/",
        )
        self.file_path = file_path

    def fetch(self) -> Optional[List[dict]]:
        if not self.file_path or not os.path.exists(self.file_path):
            return None
        try:
            if self.file_path.endswith(".csv"):
                df = pd.read_csv(self.file_path, encoding="utf-8-sig")
            elif self.file_path.endswith((".xls", ".xlsx")):
                df = pd.read_excel(self.file_path)
            else:
                return None
            return df.to_dict(orient="records")
        except Exception:
            return None

    def parse(self, raw_data: List[dict]) -> Optional[pd.DataFrame]:
        """Parse uploaded data into standard format with column mapping."""
        if not raw_data:
            return None
        df = pd.DataFrame(raw_data)
        # Try common column name patterns
        col_map = {}
        for col in df.columns:
            cl = col.lower().strip()
            if cl in ("date", "time", "day", chr(26085) + chr(26399)):
                col_map[col] = "date"
            elif cl in ("product", "name", "item", "vegetable", chr(21697) + chr(30446), chr(21517) + chr(31216)):
                col_map[col] = "product"
            elif cl in ("price", "cost", "value", "amount", chr(20215) + chr(26684)):
                col_map[col] = "price"
        df = df.rename(columns=col_map)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.dropna(subset=["product", "price"])
        if "date" in df.columns:
            df = df.dropna(subset=["date"])
        return df.reset_index(drop=True)
