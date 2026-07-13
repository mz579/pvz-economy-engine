# V2.0 迁移记录

第 7 批已把运行入口、测试和文档全部切换到 V2.0 主链。以下旧探索不再进入项目运行路径：

- Airflow 与多地区采集适配器；
- 金融化回测、夏普比率、影子价格和旧 utility 评分；
- 旧 Streamlit 入口和预测实验；
- 旧地区演示数据。

正式模块是 `crawler -> preprocess -> features -> scoring -> optimizer -> dashboard`。后续功能必须继续遵守单地区、可解释、离线可运行的 V2.0 边界。
