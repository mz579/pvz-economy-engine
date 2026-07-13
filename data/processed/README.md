# Processed data

这里的 CSV 只能由 `src.pipeline` 生成，不应手工编辑。基础契约固定为：

`date,name,price,source`

- `date`：`YYYY-MM-DD`；
- `name`：清洗后的标准蔬菜名；
- `price`：人民币元/kg；
- `source`：`xinfadi_official` 或 `local_csv_fallback`。

特征字段包括 `price_ma7`、`price_ma14`、`price_ma30`、`historical_mean`、`change_rate`、`volatility` 和 `price_rank`。`volatility` 是 30 日标准差除以 30 日均价。
