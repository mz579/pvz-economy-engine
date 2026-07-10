
"""数据源适配器抽象基类.

采用适配器模式 (Adapter Pattern)，所有具体爬虫/加载器必须继承此类，
实现 fetch() 和 parse() 方法，确保可插拔替换。
"""

from abc import ABC, abstractmethod
from typing import Optional, List
import pandas as pd


class BaseSpider(ABC):
    """多源数据适配器抽象基类.

    Attributes:
        source_name: 数据源唯一标识，与 DATA_SOURCES 中的 key 对应。
        display_name: 数据源可读名称。
        data_dir: 本地数据缓存目录。
    """

    def __init__(self, source_name: str, display_name: str, data_dir: str):
        """初始化基类.

        Args:
            source_name: 数据源唯一标识。
            display_name: 数据源可读名称。
            data_dir: 本地数据缓存目录路径。
        """
        self.source_name = source_name
        self.display_name = display_name
        self.data_dir = data_dir

    @abstractmethod
    def fetch(self, **kwargs) -> Optional[List[dict]]:
        """从数据源拉取原始数据.

        Args:
            **kwargs: 与具体数据源相关的参数（如日期范围、品种等）。

        Returns:
            原始记录列表 (每项为 dict)，或 None 表示获取失败。

        Raises:
            NotImplementedError: 子类未实现此方法时抛出。
        """
        raise NotImplementedError("子类必须实现 fetch() 方法")

    @abstractmethod
    def parse(self, raw_data: List[dict]) -> pd.DataFrame:
        """将原始数据解析为标准化的 DataFrame.

        标准化输出列: [date, product, price, source]
            - date: 日期 (datetime64)
            - product: 产品名称 (str)
            - price: 价格 (float, 元/公斤)
            - source: 数据来源标记 (str)

        Args:
            raw_data: fetch() 方法返回的原始数据。

        Returns:
            标准化后的 Pandas DataFrame。

        Raises:
            NotImplementedError: 子类未实现此方法时抛出。
        """
        raise NotImplementedError("子类必须实现 parse() 方法")

    def run(self, **kwargs) -> Optional[pd.DataFrame]:
        """执行完整的 获取→解析 流程.

        Args:
            **kwargs: 传递给 fetch() 的参数。

        Returns:
            标准化后的 DataFrame，或 None (获取/解析失败时)。
        """
        try:
            raw = self.fetch(**kwargs)
            if raw is None:
                return None
            return self.parse(raw)
        except Exception as e:
            print(f"[{self.source_name}] run() 执行失败: {e}")
            return None
