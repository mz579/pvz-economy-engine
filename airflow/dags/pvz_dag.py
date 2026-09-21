"""PvZ Economy Engine 每日数据管道 DAG（V2）。

编排链路::

    run_pipeline  ->  score_and_optimize  ->  persist_strategy
    采集+清洗+特征      评分 + 约束优化          策略落盘 JSON

与 V1 的差异（重要）
--------------------
V1 的 DAG 调用 ``src.config`` / ``src.forecast`` / ``src.valuator``，这三个模块在
V2 重写时已被 ``crawler`` / ``pipeline`` / ``scoring`` 取代，因此**原 DAG 在 V2
代码上无法导入**。本文件按 V2 的实际模块结构重写。

V2 的在线数据源仅新发地（北京）；山东寿光与广州江南以仓库内数据文件形式保留，
未做在线采集，故本 DAG **不再声明"多地区并行"**——那是 V1 的能力，V2 未继承。

依赖
----
``apache-airflow``（见 ``requirements-airflow.txt``），属于可选部署依赖，
不进入核心 ``requirements.txt``——核心运行时装了才能跑 Streamlit 看板。

用法
----
本地验证（不启动 Airflow 调度器）::

    python airflow/dags/pvz_dag.py

该 `__main__` 分支会按顺序直接调用三个 task 函数，用于确认链路可跑通。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ARGS = {
    "owner": "pvz-engine",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

# 默认求解参数（与看板默认值保持一致）
DEFAULT_MODE = "迷雾夜战"
DEFAULT_SUN = 150
DEFAULT_CELLS = 45
STRATEGY_PATH = PROJECT_ROOT / "data" / "processed" / "daily_strategy.json"


def _ensure_project_on_path() -> None:
    """Airflow 以自身工作目录启动，需手动把项目根加入 sys.path。"""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def task_run_pipeline(**context) -> dict:
    """采集 → 清洗 → 特征工程，产出 processed 宽表。

    在线采集失败时 ``run_data_pipeline`` 内部自动回退本地 CSV，
    因此该 task 在断网环境下仍可产出数据。
    """
    _ensure_project_on_path()
    from src.pipeline import run_data_pipeline

    params = context.get("params", {})
    prefer_network = params.get("prefer_network", True)

    # 允许通过 params 覆盖输出路径，便于测试隔离或按环境改写落盘位置
    overrides = {
        key: params[key]
        for key in ("raw_path", "processed_path", "metadata_path")
        if params.get(key)
    }
    artifacts = run_data_pipeline(prefer_network=prefer_network, **overrides)

    summary = {
        "rows": int(len(artifacts.data)),
        "vegetables": int(artifacts.data["name"].nunique()),
        "source": artifacts.collection.source,
        "used_fallback": bool(artifacts.collection.used_fallback),
        "processed_path": str(artifacts.processed_path),
        "date_min": artifacts.data["date"].min().strftime("%Y-%m-%d"),
        "date_max": artifacts.data["date"].max().strftime("%Y-%m-%d"),
    }
    print(f"[run_pipeline] {summary}")
    return summary


def task_score_and_optimize(**context) -> dict:
    """多因子评分 + 约束优化，产出推荐阵容与约束校验结果。"""
    _ensure_project_on_path()
    from src.dashboard import build_dashboard_model

    ti = context["ti"]
    pipeline_summary = ti.xcom_pull(task_ids="run_pipeline") or {}
    processed_path = pipeline_summary.get("processed_path")

    params = context.get("params", {})
    mode = params.get("mode", DEFAULT_MODE)
    sun = int(params.get("sun", DEFAULT_SUN))
    cells = int(params.get("cells", DEFAULT_CELLS))

    # processed_path 为 None 时交给 build_dashboard_model 用默认路径
    kwargs = {"processed_path": processed_path} if processed_path else {}
    model = build_dashboard_model(mode, sun, cells, **kwargs)

    result = model["result"]
    ranking = model["ranking"]

    # combination 是记录列表：[{name, quantity, unit_sun_cost, role, ...}, ...]
    combination = [
        {
            "name": str(item["name"]),
            "quantity": int(item["quantity"]),
            "role": str(item.get("role", "")),
            "subtotal_sun": int(item.get("subtotal_sun", 0)),
        }
        for item in result["combination"]
    ]

    # 约束校验结果逐条记录，便于失败时定位
    checks = result.get("constraint_checks") or {}
    if isinstance(checks, dict):
        failed = [k for k, v in checks.items() if v is False]
    else:
        failed = []

    summary = {
        "mode": mode,
        "available_sun": sun,
        "available_cells": cells,
        "plants_ranked": int(len(ranking)),
        "top_plant": str(ranking.iloc[0]["name"]) if len(ranking) else None,
        "combination": combination,
        "total_sun_cost": int(result.get("total_sun_cost", 0)),
        "total_plants": int(result.get("total_plants", 0)),
        "per_plant_limit": int(result.get("per_plant_limit", 0)),
        "failed_constraints": failed,
        "all_constraints_met": bool(result["all_constraints_met"]),
        "method": str(result.get("method", "")),
        "fallback_reason": result.get("fallback_reason"),
        "score_column": result["score_column"],
    }
    print(f"[score_and_optimize] {summary}")
    return summary


def task_persist_strategy(**context) -> dict:
    """把当日策略落盘为 JSON，供下游任务或看板读取。"""
    ti = context["ti"]
    pipeline_summary = ti.xcom_pull(task_ids="run_pipeline") or {}
    strategy = ti.xcom_pull(task_ids="score_and_optimize") or {}

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pipeline": pipeline_summary,
        "strategy": strategy,
    }
    STRATEGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[persist_strategy] 已写入 {STRATEGY_PATH}")
    return {"strategy_path": str(STRATEGY_PATH)}


with DAG(
    "pvz_economy_engine",
    default_args=DEFAULT_ARGS,
    description="每日菜价采集 → 多因子评分 → 约束优化 → 策略落盘",
    schedule="@daily",
    start_date=datetime(2026, 7, 11),
    catchup=False,
    tags=["pvz", "data-engineering"],
) as dag:
    run_pipeline = PythonOperator(
        task_id="run_pipeline",
        python_callable=task_run_pipeline,
    )
    score_and_optimize = PythonOperator(
        task_id="score_and_optimize",
        python_callable=task_score_and_optimize,
    )
    persist_strategy = PythonOperator(
        task_id="persist_strategy",
        python_callable=task_persist_strategy,
    )

    run_pipeline >> score_and_optimize >> persist_strategy


if __name__ == "__main__":
    # 本地冒烟：不启动 Airflow，直接顺序调用三个 task 函数。
    # 用一个极简的 context 桩替代 Airflow 的 ti（XCom 用字典模拟）。
    class _FakeTI:
        def __init__(self) -> None:
            self._store: dict = {}

        def xcom_pull(self, task_ids: str):
            return self._store.get(task_ids)

        def xcom_push(self, task_ids: str, value) -> None:
            self._store[task_ids] = value

    _ti = _FakeTI()
    _ctx = {"ti": _ti, "params": {"prefer_network": False}}

    _ti.xcom_push("run_pipeline", task_run_pipeline(**_ctx))
    _ti.xcom_push("score_and_optimize", task_score_and_optimize(**_ctx))
    print(task_persist_strategy(**_ctx))
