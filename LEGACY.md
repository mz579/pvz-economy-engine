# V2.0 Legacy 清单

这些文件来自旧版探索，不属于 V2.0 主线。第 1 批不做物理删除，以便后续替换时核对；第 7 批端到端验证通过后再统一清理。

## 明确停止扩展

- `airflow/`：多地区定时调度，超出 V2.0 范围。
- `src/backtester.py`：金融化回测、夏普比率和最大回撤。
- `src/adapters/shouguang_spider.py`、`src/adapters/guangzhou_spider.py`：多地区适配器。
- `src/adapters/custom_upload_adapter.py`：多格式上传不进入核心链路。
- `data/shouguang/`、`data/guangzhou/`：旧地区演示数据。
- `report.html`：旧版静态分析报告。
- `Dockerfile`、`docker-compose.yml`：可选部署实验，当前不维护。
- `learning_hub.html`、`resume.docx`、`build_resume.py`：与项目运行无关。

## 兼容期保留但等待替换

- `src/valuator.py`：第 4 批由 `src/scoring.py` 的 V2.0 公式替换。
- `src/optimizer.py`：第 5 批重写约束和 fallback。
- `src/app.py`：第 6 批由根目录 `app.py` 的 V2.0 页面替换。
- `src/forecast.py`：不接入 V2.0 核心链；项目稳定后再决定是否保留。
- `src/config.py` 与 `src/adapters/`：第 2 批收敛为北京新发地加本地 CSV fallback。

## 清理条件

只有在第 7 批确认以下条件后，才删除 legacy 文件：

1. 离线数据能够从清洗一路运行到推荐结果；
2. Streamlit 页面能够通过根目录 `app.py` 启动；
3. README 的安装与运行命令已在干净环境验证；
4. 测试不再导入任何 legacy 模块。
