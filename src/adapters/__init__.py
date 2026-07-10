
"""可插拔多源数据适配器模块.

通过适配器模式 (Adapter Pattern) 解耦数据采集层，
支持北京新发地、山东寿光、广州江南等多地区数据源无缝切换。
"""

from src.adapters.base_spider import BaseSpider
from src.adapters.xinfadi_spider import XinfadiSpider
from src.adapters.local_csv_loader import LocalCSVLoader

__all__ = ["BaseSpider", "XinfadiSpider", "LocalCSVLoader"]
