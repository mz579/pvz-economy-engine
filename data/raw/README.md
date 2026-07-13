# Raw data

`python -m src.pipeline` 会在这里生成：

- `latest_prices.csv`：在线响应或本地 fallback 的原始字段快照；
- `latest_prices.metadata.json`：采集时间、来源、是否回退、日期范围、单位和窗口。

生成文件不提交到 Git。官方数据来自北京新发地公开价格页面；当前接口不可用、返回空数据或结构变化时，流水线自动改用 `data/fallback/vegetable_prices.csv`。
