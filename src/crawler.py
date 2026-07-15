"""Price collection for the V2 data pipeline.

The public Beijing Xinfadi endpoint is attempted first.  Network errors,
schema changes, and empty responses are all treated as recoverable conditions:
the bundled CSV remains the deterministic offline source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from src.runtime import runtime_path


XINFADI_PRICE_PAGE = "https://www.xinfadi.com.cn/priceDetail.html"
XINFADI_API_URL = "https://www.xinfadi.com.cn/getPriceData.html"
DEFAULT_FALLBACK_PATH = runtime_path("data/fallback/vegetable_prices.csv")


@dataclass(frozen=True)
class CollectionResult:
    """A collected data frame plus traceable fallback metadata."""

    data: pd.DataFrame
    source: str
    used_fallback: bool
    message: str
    source_url: str | None = None


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Extract record dictionaries from common paginated JSON envelopes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("list", "rows", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    nested = payload.get("data")
    if nested is not None and nested is not payload:
        return _records_from_payload(nested)
    return []


def _first_present(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def fetch_xinfadi_prices(
    *,
    days: int = 30,
    page_size: int = 200,
    timeout: float = 8.0,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch recent public price records from Beijing Xinfadi.

    The endpoint is intentionally isolated here so a future site schema change
    cannot leak into cleaning, scoring, or the Streamlit page.

    Raises:
        requests.RequestException: when the website is unavailable.
        ValueError: when the response is not usable price data.
    """

    if days < 1:
        raise ValueError("days 必须大于 0")

    today = date.today()
    client = session or requests.Session()
    response = client.post(
        XINFADI_API_URL,
        data={
            "limit": int(page_size),
            "current": 1,
            "pubDateStartTime": (today - timedelta(days=days - 1)).isoformat(),
            "pubDateEndTime": today.isoformat(),
            "prodPcatid": 1186,
        },
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; pvz-economy-engine/2.0)",
            "Accept": "application/json, text/plain, */*",
            "Referer": XINFADI_PRICE_PAGE,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("新发地接口未返回 JSON 数据") from exc

    normalized: list[dict[str, Any]] = []
    for record in _records_from_payload(payload):
        normalized.append(
            {
                "date": _first_present(
                    record, ("pubDate", "publishDate", "date", "发布日期")
                ),
                "name": _first_present(
                    record, ("prodName", "productName", "name", "品名")
                ),
                "price": _first_present(
                    record, ("avgPrice", "averagePrice", "price", "均价")
                ),
                "source": "xinfadi_official",
                "unit": _first_present(
                    record, ("unitInfo", "unit", "priceUnit", "单位")
                ),
            }
        )

    result = pd.DataFrame(
        normalized, columns=["date", "name", "price", "source", "unit"]
    )
    if result.empty or result[["date", "name", "price"]].dropna(how="any").empty:
        raise ValueError("新发地接口返回为空或字段结构已变化")
    return result


def load_local_fallback(
    path: Path | str = DEFAULT_FALLBACK_PATH,
) -> pd.DataFrame:
    """Load the deterministic local CSV without requiring network access."""

    fallback_path = Path(path)
    if not fallback_path.is_file():
        raise FileNotFoundError(f"本地 fallback 不存在: {fallback_path}")

    data = pd.read_csv(fallback_path)
    data = data.rename(columns={"product": "name"})
    required = {"date", "name", "price"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"本地 fallback 缺少字段: {', '.join(sorted(missing))}")
    data = data.copy()
    data["source"] = "local_csv_fallback"
    if "unit" not in data.columns:
        data["unit"] = "元/kg"
    return data[["date", "name", "price", "source", "unit"]]


def collect_price_data(
    *,
    prefer_network: bool = True,
    fallback_path: Path | str = DEFAULT_FALLBACK_PATH,
    timeout: float = 8.0,
) -> CollectionResult:
    """Collect online data when possible and always retain an offline route."""

    failure: Exception | None = None
    if prefer_network:
        try:
            online = fetch_xinfadi_prices(timeout=timeout)
            return CollectionResult(
                data=online,
                source="xinfadi_official",
                used_fallback=False,
                message="已读取北京新发地公开价格数据。",
                source_url=XINFADI_PRICE_PAGE,
            )
        except (requests.RequestException, ValueError, KeyError) as exc:
            failure = exc

    fallback = load_local_fallback(fallback_path)
    if failure is None:
        message = "离线模式：已读取本地 CSV fallback。"
    else:
        message = f"在线数据不可用，已回退本地 CSV：{failure}"
    return CollectionResult(
        data=fallback,
        source="local_csv_fallback",
        used_fallback=True,
        message=message,
        source_url=str(Path(fallback_path)),
    )
