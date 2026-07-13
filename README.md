# 基于真实菜价与植物大战僵尸策略的末日蔬菜种植推荐系统

> PvZ Economy Engine V2.0 正在按批次重构。当前完成第 1 批：项目结构与版本边界整理。

本项目把北京地区真实蔬菜价格与植物策略属性结合，回答一个可解释的问题：在有限阳光、格子和攻防需求下，末日环境中种植哪些蔬菜植物最有性价比。

## V2.0 目标链路

```text
北京新发地真实菜价或本地 CSV
    -> 日期、菜名和价格单位清洗
    -> 移动均价、涨跌幅、波动率和价格分位数
    -> 植物与现实蔬菜映射
    -> 末日性价比指数与推荐理由
    -> 阳光/格子/攻防约束组合优化
    -> PvZ 风格 Streamlit 看板
```

## 版本边界

V2.0 只保证一个地区、一个可解释模型和一条可离线运行的主链。以下内容不属于本版本：

- Airflow 调度和多地区 SaaS；
- Alpha、夏普比率等金融指标；
- 复杂回测、影子价格和金融化叙事；
- Prophet、XGBoost 等非必要重模型；
- 官方 PvZ 图片、音效或其他版权素材。

旧仓库中的相关文件暂时保留用于迁移核对，但已经标记为 legacy，不应继续扩展。详见 [LEGACY.md](LEGACY.md)。

## 当前状态

| 批次 | 状态 | 内容 |
|---|---|---|
| 第 1 批 | 已完成 | 目录、入口、依赖、README、项目规则和 smoke test |
| 第 2 批 | 待执行 | 北京新发地采集、清洗、特征与离线 fallback |
| 第 3 批 | 待执行 | 12-15 种植物参数与现实蔬菜映射 |
| 第 4 批 | 待执行 | 可解释末日性价比评分 |
| 第 5 批 | 待执行 | PuLP 组合优化与贪心 fallback |
| 第 6 批 | 待执行 | PvZ 风格 Streamlit 页面 |
| 第 7 批 | 待执行 | 端到端联调、文档和 legacy 清理 |

当前 `cli.py` 与 `src/app.py` 仍是 V1 兼容实现，只用于保证重构期间项目可启动。V2.0 业务链将在后续批次逐步替换。

## 项目结构

```text
app.py                       # V2.0 统一 Streamlit 入口；当前转发到兼容页面
assets/
  style.css                  # 第 6 批启用的样式入口
  plant_icons/               # 自绘、emoji 或允许再分发的图标
data/
  raw/                       # 原始采集数据及来源元数据
  processed/                 # 清洗和特征数据，不手工编辑
  plants.csv                 # 当前兼容植物表，第 3 批重建
src/                         # 采集、清洗、评分、优化和页面代码
tests/                       # 标准库 unittest 测试
AGENTS.md                    # 后续 Codex 执行规则
LEGACY.md                    # 非 V2.0 主线清单
```

## 快速开始

建议使用 Python 3.10 或 3.11。

```bash
python -m venv .venv
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

运行兼容 CLI：

```bash
python cli.py --sun 150 --cells 20
```

运行 Streamlit：

```bash
streamlit run app.py
```

## 数据与素材原则

- 原始菜价必须记录来源、采集时间、原始单位和转换规则。
- 网络数据源不可用时必须自动使用仓库内的离线样例。
- `data/processed/` 文件只能由清洗流程生成。
- 植物图标只能使用自绘、emoji 或明确允许再分发的资源。

## 许可证与说明

本项目是数据分析与运筹优化练习，不隶属于植物大战僵尸版权方。项目不会提交官方游戏素材。
