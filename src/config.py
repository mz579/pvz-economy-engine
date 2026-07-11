"""Global configuration module - data source registry and runtime config.

All data sources are registered in the DATA_SOURCES dictionary,
switching is done via CURRENT_SOURCE variable or environment variable.
"""
import os
from typing import Dict, Any


DATA_SOURCES: Dict[str, Dict[str, Any]] = {
    "xinfadi": {
        "adapter_class": "src.adapters.xinfadi_spider.XinfadiSpider",
        "display_name": chr(21271) + chr(20140) + chr(26032) + chr(21457) + chr(22320) + chr(25209) + chr(21457) + chr(24066) + chr(22330),
        "description": chr(21271) + chr(20140) + chr(26032) + chr(21457) + chr(22320) + chr(23448) + chr(32593) + chr(24320) + chr(20844) + chr(24320) + chr(26085) + chr(24230) + chr(33756) + chr(33756) + chr(20215) + chr(26684) + chr(25968) + chr(25454) + chr(65288) + chr(40664) + chr(35748) + chr(65289),
        "data_dir": "data/beijing/",
    },
    "shouguang": {
        "adapter_class": "src.adapters.shouguang_spider.ShouguangSpider",
        "display_name": chr(23665) + chr(19996) + chr(20852) + chr(20809) + chr(33756) + chr(33756) + chr(20215) + chr(26684) + chr(25351) + chr(25968),
        "description": chr(23665) + chr(19996) + chr(20852) + chr(20809) + chr(33756) + chr(33756) + chr(20215) + chr(26684) + chr(25351) + chr(25968) + chr(65292) + chr(22269) + chr(20869) + chr(37325) + chr(35201) + chr(33756) + chr(33756) + chr(38598) + chr(25955) + chr(22320),
        "data_dir": "data/shouguang/",
    },
    "guangzhou": {
        "adapter_class": "src.adapters.guangzhou_spider.GuangzhouSpider",
        "display_name": chr(24191) + chr(24030) + chr(27743) + chr(21335) + chr(26524) + chr(33756) + chr(24066) + chr(22330),
        "description": chr(35206) + chr(30422) + chr(21335) + chr(26041) + chr(28909) + chr(33756) + chr(26524) + chr(21697) + chr(21697) + chr(24066) + chr(22330),
        "data_dir": "data/guangzhou/",
    },
    "custom_upload": {
        "adapter_class": "src.adapters.custom_upload_adapter.CustomUploadAdapter",
        "display_name": chr(19978) + chr(20256) + chr(19978) + chr(20256) + chr(25968) + chr(25454) + chr(20837) + chr(20837) + chr(20256) + chr(25454),
        "description": chr(29992) + chr(25143) + chr(33258) + chr(34892) + chr(19978) + chr(21475) + chr(20256) + chr(20837) + chr(20837) + chr(20256) + chr(25968) + chr(25454),
        "data_dir": "data/custom/",
    },
    "local_csv": {
        "adapter_class": "src.adapters.local_csv_loader.LocalCSVLoader",
        "display_name": chr(26412) + chr(22320) + chr(67) + chr(83) + chr(86) + chr(25991) + chr(20214) + chr(21152) + chr(36733) + chr(36733),
        "description": chr(35835) + chr(21462) + chr(100) + chr(97) + chr(116) + chr(97) + chr(47) + chr(102) + chr(97) + chr(108) + chr(108) + chr(98) + chr(97) + chr(99) + chr(107) + chr(47) + chr(30446) + chr(24405) + chr(19979) + chr(30340) + chr(31163) + chr(32447) + chr(67) + chr(83) + chr(86) + chr(25991) + chr(20214) + chr(20316) + chr(20316) + chr(22771) + chr(24213),
        "data_dir": "data/fallback/",
    },
}


_source_env = os.environ.get("PVZ_DATA_SOURCE", "").strip().lower()
_source_env = _source_env if _source_env in DATA_SOURCES else ""

CURRENT_SOURCE: str = _source_env or "xinfadi"

REQUEST_TIMEOUT: int = 10
USER_AGENTS: list = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
]

CACHE_ENABLED: bool = True
CACHE_MAX_DAYS: int = 90


def get_current_source_config() -> Dict[str, Any]:
    if CURRENT_SOURCE not in DATA_SOURCES:
        raise KeyError(
            f"Unknown data source: {CURRENT_SOURCE}, "
            f"available: {list(DATA_SOURCES.keys())}"
        )
    return DATA_SOURCES[CURRENT_SOURCE]


def list_available_sources() -> Dict[str, str]:
    return {k: v["display_name"] for k, v in DATA_SOURCES.items()}
