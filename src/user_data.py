"""User-supplied regional price data parsing and feature preparation."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.features import add_price_features
from src.preprocess import clean_price_data


SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")


def read_price_csv_bytes(content: bytes) -> pd.DataFrame:
    """Read UTF-8 or common Chinese-encoded CSV bytes."""

    if not content:
        raise ValueError("上传的 CSV 是空文件")

    errors: list[str] = []
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except pd.errors.EmptyDataError as exc:
            raise ValueError("上传的 CSV 没有表头或数据") from exc
        except pd.errors.ParserError as exc:
            raise ValueError(f"CSV 格式无法解析: {exc}") from exc
    raise ValueError("CSV 编码无法识别，请另存为 UTF-8 或 GB18030")


def prepare_uploaded_price_data(
    content: bytes,
    *,
    region_name: str,
    history_window: int = 30,
) -> pd.DataFrame:
    """Clean and feature-engineer one region's uploaded CSV in memory."""

    region = region_name.strip() or "未命名地区"
    raw = read_price_csv_bytes(content)
    cleaned = clean_price_data(raw, source_name=f"user_upload:{region}")
    if cleaned.empty:
        raise ValueError("CSV 清洗后没有有效记录，请检查日期、菜名和正数价格")
    return add_price_features(cleaned, history_window=history_window)
