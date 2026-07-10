
"""全局配置模块 — 数据源注册表与运行时配置.

所有数据源在 DATA_SOURCES 字典中注册，
通过 CURRENT_SOURCE 变量或环境变量实现一键切换。
"""

import os
from typing import Dict, Any

# ---------------------------------------------------------------------------
# 数据源注册表
# ---------------------------------------------------------------------------
# 每个条目包含:
#   adapter_class : 适配器类全路径 (用于动态导入)
#   display_name  : 前端展示名称
#   description   : 数据源简介

DATA_SOURCES: Dict[str, Dict[str, Any]] = {
    "xinfadi": {
        "adapter_class": "src.adapters.xinfadi_spider.XinfadiSpider",
        "display_name": "北京新发地批发市场",
        "description": "北京新发地官网公开日度蔬菜价格数据（默认）",
        "data_dir": "data/beijing/",
    },
    "shouguang": {
        "adapter_class": "src.adapters.shouguang_spider.ShouguangSpider",
        "display_name": "山东寿光蔬菜价格指数",
        "description": "山东寿光蔬菜价格指数，国内重要蔬菜集散地",
        "data_dir": "data/shouguang/",
    },
    "local_csv": {
        "adapter_class": "src.adapters.local_csv_loader.LocalCSVLoader",
        "display_name": "本地 CSV 文件加载器",
        "description": "读取 data/fallback/ 目录下的离线 CSV 文件作为兜底",
        "data_dir": "data/fallback/",
    },
}

# ---------------------------------------------------------------------------
# 运行时配置
# ---------------------------------------------------------------------------

# 当前激活的数据源 key，优先读取环境变量，方便 Docker/Airflow 注入
_source_env = os.environ.get("PVZ_DATA_SOURCE", "").strip().lower()
_source_env = _source_env if _source_env in DATA_SOURCES else ""

CURRENT_SOURCE: str = _source_env or "xinfadi"

# 爬虫通用设置
REQUEST_TIMEOUT: int = 10  # 请求超时秒数
USER_AGENTS: list = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
]

# 缓存设置
CACHE_ENABLED: bool = True
CACHE_MAX_DAYS: int = 90


def get_current_source_config() -> Dict[str, Any]:
    """获取当前激活数据源的配置字典.

    Returns:
        当前数据源的配置字典。

    Raises:
        KeyError: 当 CURRENT_SOURCE 在 DATA_SOURCES 中不存在时。
    """
    if CURRENT_SOURCE not in DATA_SOURCES:
        raise KeyError(
            f"未知数据源: {CURRENT_SOURCE}，"
            f"可选: {list(DATA_SOURCES.keys())}"
        )
    return DATA_SOURCES[CURRENT_SOURCE]


def list_available_sources() -> Dict[str, str]:
    """列出所有可用数据源的名称与显示名.

    Returns:
        {key: display_name} 字典。
    """
    return {k: v["display_name"] for k, v in DATA_SOURCES.items()}
