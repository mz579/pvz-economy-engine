"""PvZ Economy Engine DAG - daily automated pipeline with multi-source support."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {"owner": "pvz-engine", "retries": 1, "retry_delay": timedelta(minutes=5)}

REGIONS = ["xinfadi", "shouguang", "guangzhou"]


def _import_src():
    import sys; sys.path.insert(0, "/app")


def task_extract(**context):
    _import_src()
    from src.config import DATA_SOURCES, CURRENT_SOURCE
    import importlib
    source_key = context.get("params", {}).get("source", CURRENT_SOURCE)
    cfg = DATA_SOURCES.get(source_key)
    if not cfg:
        print(f"Unknown source: {source_key}")
        return
    mod_path, cls_name = cfg["adapter_class"].rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    adapter = getattr(mod, cls_name)()
    raw = adapter.fetch()
    if raw:
        df = adapter.parse(raw)
        out_path = cfg["data_dir"] + "latest.csv"
        if df is not None:
            import os
            os.makedirs(cfg["data_dir"], exist_ok=True)
            df.to_csv(out_path, index=False)
            print(f"Extracted {len(df)} records for {source_key}")
    else:
        print(f"No data extracted for {source_key}")


def task_transform(**context):
    _import_src()
    import pandas as pd
    from src.preprocess import standardize_price_data, add_time_features
    from src.config import DATA_SOURCES, CURRENT_SOURCE
    source_key = context.get("params", {}).get("source", CURRENT_SOURCE)
    cfg = DATA_SOURCES.get(source_key, {})
    in_path = (cfg.get("data_dir", "data/fallback/") + "latest.csv").replace("//", "/")
    df = pd.read_csv(in_path) if __import__("os").path.exists(in_path) else pd.DataFrame()
    if df.empty:
        print(f"No data to transform for {source_key}")
        return
    df["date"] = pd.to_datetime(df["date"])
    df = standardize_price_data(df)
    df = add_time_features(df)
    import os; os.makedirs("data/processed/", exist_ok=True)
    df.to_csv(f"data/processed/latest_{source_key}.csv", index=False)
    print(f"Transformed {len(df)} rows for {source_key}")


def task_forecast(**context):
    _import_src()
    import pandas as pd
    from src.forecast import forecast_all
    source_key = context.get("params", {}).get("source", "xinfadi")
    in_path = f"data/processed/latest_{source_key}.csv"
    if not __import__("os").path.exists(in_path):
        in_path = "data/fallback/vegetable_prices.csv"
    df = pd.read_csv(in_path)
    df["date"] = pd.to_datetime(df["date"])
    fc = forecast_all(df)
    import os; os.makedirs("data/processed/", exist_ok=True)
    fc.to_csv(f"data/processed/forecast_{source_key}.csv", index=False)
    print(f"Forecasted {len(fc)} products for {source_key}")


def task_valuate(**context):
    _import_src()
    import pandas as pd
    from src.valuator import calculate_utility, calc_deviation
    source_key = context.get("params", {}).get("source", "xinfadi")
    df_plants = pd.read_csv("data/plants.csv")
    in_path = f"data/processed/latest_{source_key}.csv"
    if not __import__("os").path.exists(in_path):
        in_path = "data/fallback/vegetable_prices.csv"
    df_prices = pd.read_csv(in_path)
    df_prices["date"] = pd.to_datetime(df_prices["date"])
    du = calculate_utility(df_plants)
    dv = calc_deviation(df_prices, du)
    import os; os.makedirs("data/processed/", exist_ok=True)
    dv.to_csv(f"data/processed/valuation_{source_key}.csv", index=False)
    print(f"Valued {len(dv)} plants for {source_key}")


def task_optimize(**context):
    _import_src()
    import pandas as pd
    from src.optimizer import run_optimization
    from src.valuator import calculate_utility, calc_deviation
    source_key = context.get("params", {}).get("source", "xinfadi")
    df_plants = pd.read_csv("data/plants.csv")
    in_path = f"data/processed/latest_{source_key}.csv"
    if not __import__("os").path.exists(in_path):
        in_path = "data/fallback/vegetable_prices.csv"
    df_prices = pd.read_csv(in_path)
    df_prices["date"] = pd.to_datetime(df_prices["date"])
    du = calculate_utility(df_plants)
    dv = calc_deviation(df_prices, du)
    dm = df_plants.merge(du[["name", "utility"]], on="name")
    r = run_optimization(dm, dv, 150, 20)
    import os; os.makedirs("data/processed/", exist_ok=True)
    import json
    with open(f"data/processed/strategy_{source_key}.json", "w") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print(f"Optimized for {source_key}: {r['strategy']}")


# Main DAG
with DAG("pvz_economy_engine", default_args=default_args,
         schedule_interval="@daily", start_date=datetime(2026, 7, 11),
         catchup=False, tags=["pvz", "economy"]) as dag:
    t_extract = PythonOperator(task_id="extract", python_callable=task_extract)
    t_transform = PythonOperator(task_id="transform", python_callable=task_transform)
    t_forecast = PythonOperator(task_id="forecast", python_callable=task_forecast)
    t_valuate = PythonOperator(task_id="valuate", python_callable=task_valuate)
    t_optimize = PythonOperator(task_id="optimize", python_callable=task_optimize)
    t_extract >> t_transform >> [t_forecast, t_valuate] >> t_optimize

# Per-region DAGs
for region in REGIONS:
    dag_id = f"pvz_economy_{region}"
    with DAG(dag_id, default_args=default_args,
             schedule_interval="@daily", start_date=datetime(2026, 7, 11),
             catchup=False, tags=["pvz", "economy", region],
             params={"source": region}) as region_dag:
        t1 = PythonOperator(task_id=f"extract_{region}", python_callable=task_extract,
                            op_kwargs={"params": {"source": region}})
        t2 = PythonOperator(task_id=f"transform_{region}", python_callable=task_transform,
                            op_kwargs={"params": {"source": region}})
        t3 = PythonOperator(task_id=f"forecast_{region}", python_callable=task_forecast,
                            op_kwargs={"params": {"source": region}})
        t4 = PythonOperator(task_id=f"valuate_{region}", python_callable=task_valuate,
                            op_kwargs={"params": {"source": region}})
        t5 = PythonOperator(task_id=f"optimize_{region}", python_callable=task_optimize,
                            op_kwargs={"params": {"source": region}})
        t1 >> t2 >> [t3, t4] >> t5
