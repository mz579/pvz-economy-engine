# PvZ Economy Engine v1.0

Data-driven Plants vs. Zombies economic decision engine with multi-source data adapters, quantitative valuation, MIP optimization, style rotation, and strategy backtesting.

## Pipeline

```
Multi-source data (Adapter Layer)
    → Standardization / Feature Engineering
    → Price Forecasting (7-day outlook)
    → Relative Valuation (anchor-based)
    → MIP Portfolio Optimization (PuLP)
    → Shadow Price Analysis
    → Strategy Backtesting (wave simulation)
```

## Quick Start

```bash
pip install -r requirements.txt
python cli.py --sun 150 --cells 20
```

Open `report.html` for the full analysis report.

## Dashboard

```bash
streamlit run src/app.py
```

Features:
- **Region selector**: switch between Beijing Xinfadi / Shouguang / Guangzhou data sources
- **Zombie factor sliders**: style rotation (swarm/tank/air)
- **Shadow price analysis**: marginal value of sun and cells
- **Valuation deviation chart**: identify undervalued/overvalued plants
- **Strategy cards**: optimal plant composition with utility scores

## Modules

| Module | Description |
|--------|-------------|
| src/adapters/ | Pluggable data source adapters (Adapter Pattern) |
| src/adapters/base_spider.py | Abstract base class |
| src/adapters/xinfadi_spider.py | Beijing Xinfadi market |
| src/adapters/shouguang_spider.py | Shandong Shouguang index |
| src/adapters/guangzhou_spider.py | Guangzhou Jiangnan market |
| src/adapters/local_csv_loader.py | Local CSV fallback loader |
| src/adapters/custom_upload_adapter.py | User-uploaded Excel/CSV |
| src/preprocess.py | Standardization + alias mapping + features |
| src/forecast.py | 7-day price forecasting (seasonal decomposition) |
| src/valuator.py | Relative valuation (anchor Peashooter = U 1.0) |
| src/optimizer.py | PuLP MIP optimizer with shadow prices |
| src/backtester.py | Discrete event wave simulator |
| src/app.py | Streamlit interactive dashboard |
| src/config.py | Global config + data source registry |
| airflow/dags/pvz_dag.py | Daily automated pipeline (multi-region) |

## Data Sources

Registered in `src/config.py`. Default: Beijing Xinfadi.
Switch via environment variable `PVZ_DATA_SOURCE` or Streamlit dropdown.

## V1.0 Highlights

- **MIP optimizer**: PuLP mixed-integer programming with true shadow prices from dual variables
- **Cash-flow constraint**: dynamic payback period (30s sun recovery) for realistic sustainability
- **Multi-source architecture**: 5 data source adapters with unified interface
- **Style rotation**: zombie factor weights dynamically adjust plant utility scores
- **Backtesting**: Sharp ratio, max drawdown, wave-by-wave comparison vs baselines

## Docker

```bash
docker compose up -d
```
