# PvZ Economy Engine v1.0

Data-driven Plants vs. Zombies economic decision engine.

## Quick Start
`ash
pip install -r requirements.txt
python cli.py --sun 150 --cells 20
`
Open report.html for the full analysis.

## Pipeline
1. Extract: multi-source data adapters
2. Transform: standardization + feature engineering
3. Forecast: seasonal decomposition + exponential smoothing
4. Valuate: anchor-based relative valuation model
5. Optimize: greedy knapsack with shadow prices
6. Backtest: discrete event wave simulator

## Dashboard
`ash
streamlit run src/app.py
`

## Modules
| Module | Description |
|--------|-------------|
| src/adapters/ | Pluggable data source adapters |
| src/preprocess.py | Data cleaning + features |
| src/forecast.py | 7-day price prediction |
| src/valuator.py | Relative valuation |
| src/optimizer.py | Portfolio optimization |
| src/backtester.py | Wave simulation + metrics |
| src/app.py | Streamlit dashboard |
