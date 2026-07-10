"""PvZ Economy Engine DAG — daily automated pipeline."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator


def task_extract():
    import sys; sys.path.insert(0, "/app")
    from src.adapters import LocalCSVLoader
    loader = LocalCSVLoader()
    raw = loader.fetch()
    print(f"Extracted {len(raw)} records")


def task_transform():
    import sys; sys.path.insert(0, "/app")
    import pandas as pd
    from src.preprocess import standardize_price_data, add_time_features
    df = pd.read_csv("data/fallback/vegetable_prices.csv")
    df["date"] = pd.to_datetime(df["date"])
    df = standardize_price_data(df)
    df = add_time_features(df)
    df.to_csv("data/processed/latest.csv", index=False)
    print(f"Transformed {len(df)} rows")


def task_forecast():
    import sys; sys.path.insert(0, "/app")
    import pandas as pd
    from src.forecast import forecast_all
    df = pd.read_csv("data/fallback/vegetable_prices.csv")
    df["date"] = pd.to_datetime(df["date"])
    fc = forecast_all(df)
    fc.to_csv("data/processed/forecast.csv", index=False)
    print(f"Forecasted {len(fc)} products")


def task_valuate():
    import sys; sys.path.insert(0, "/app")
    import pandas as pd
    from src.valuator import calculate_utility, calc_deviation
    df_plants = pd.read_csv("data/plants.csv")
    df_prices = pd.read_csv("data/fallback/vegetable_prices.csv")
    df_prices["date"] = pd.to_datetime(df_prices["date"])
    du = calculate_utility(df_plants)
    dv = calc_deviation(df_prices, du)
    dv.to_csv("data/processed/valuation.csv", index=False)
    print(f"Valued {len(dv)} plants")


def task_optimize():
    import sys; sys.path.insert(0, "/app")
    import pandas as pd
    from src.optimizer import run_optimization
    df_plants = pd.read_csv("data/plants.csv")
    df_prices = pd.read_csv("data/fallback/vegetable_prices.csv")
    df_prices["date"] = pd.to_datetime(df_prices["date"])
    from src.valuator import calculate_utility, calc_deviation
    du = calculate_utility(df_plants)
    dv = calc_deviation(df_prices, du)
    dm = df_plants.merge(du[["name","utility"]], on="name")
    r = run_optimization(dm, dv, 150, 20)
    print(f"Optimized: {r['strategy']}")


default_args = {"owner": "pvz-engine", "retries": 1, "retry_delay": timedelta(minutes=5)}

with DAG("pvz_economy_engine", default_args=default_args,
         schedule_interval="@daily", start_date=datetime(2026, 7, 11),
         catchup=False, tags=["pvz", "economy"]) as dag:
    t1 = PythonOperator(task_id="extract", python_callable=task_extract)
    t2 = PythonOperator(task_id="transform", python_callable=task_transform)
    t3 = PythonOperator(task_id="forecast", python_callable=task_forecast)
    t4 = PythonOperator(task_id="valuate", python_callable=task_valuate)
    t5 = PythonOperator(task_id="optimize", python_callable=task_optimize)
    t1 >> t2 >> [t3, t4] >> t5
