"""Acceptance tests for the scheduled Airflow DAG.

Airflow 本身是可选依赖（见 requirements-airflow.txt），未安装时本测试用
最小桩替代，不影响其余用例。测试覆盖三件事：

1. DAG 的任务依赖链与调度元信息正确
2. 三个任务函数在断网（offline fallback）下可真实跑通
3. 策略 JSON 正确落盘，且约束校验全部通过
"""

from __future__ import annotations

import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DAG_PATH = ROOT / "airflow" / "dags" / "pvz_dag.py"


def _install_airflow_stub() -> list[tuple[str, str]]:
    """安装最小 airflow 桩；返回列表用于收集任务依赖边。"""
    edges: list[tuple[str, str]] = []

    class _DAG:
        def __init__(self, dag_id: str, **kwargs) -> None:
            self.dag_id = dag_id
            self.kwargs = kwargs

        def __enter__(self) -> "_DAG":
            return self

        def __exit__(self, *exc) -> bool:
            return False

    class _PythonOperator:
        def __init__(self, task_id: str, python_callable, **kwargs) -> None:
            self.task_id = task_id
            self.python_callable = python_callable

        def __rshift__(self, other: "_PythonOperator") -> "_PythonOperator":
            edges.append((self.task_id, other.task_id))
            return other

    airflow = types.ModuleType("airflow")
    airflow.DAG = _DAG
    operators = types.ModuleType("airflow.operators")
    operators_python = types.ModuleType("airflow.operators.python")
    operators_python.PythonOperator = _PythonOperator
    operators.python = operators_python

    sys.modules["airflow"] = airflow
    sys.modules["airflow.operators"] = operators
    sys.modules["airflow.operators.python"] = operators_python
    return edges


class _FakeTaskInstance:
    """模拟 Airflow 的 TaskInstance，仅实现本 DAG 用到的 XCom 读写。"""

    def __init__(self) -> None:
        self._store: dict = {}

    def xcom_pull(self, task_ids: str):
        return self._store.get(task_ids)

    def xcom_push(self, task_ids: str, value) -> None:
        self._store[task_ids] = value


class AirflowDagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.edges = _install_airflow_stub()
        # run_name 刻意不用 __main__，避免加载时执行 DAG 自带的本机冒烟分支
        cls.ns = runpy.run_path(str(DAG_PATH), run_name="pvz_dag_under_test")

    def test_task_dependency_chain(self) -> None:
        self.assertEqual(
            self.edges,
            [
                ("run_pipeline", "score_and_optimize"),
                ("score_and_optimize", "persist_strategy"),
            ],
        )

    def test_dag_schedule_metadata(self) -> None:
        dag = self.ns["dag"]
        self.assertEqual(dag.dag_id, "pvz_economy_engine")
        self.assertEqual(dag.kwargs.get("schedule"), "@daily")
        self.assertFalse(dag.kwargs.get("catchup"))
        self.assertEqual(dag.kwargs["default_args"]["retries"], 2)

    def test_task_chain_runs_offline_and_reports_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            ns = self.ns
            # 把落盘路径改到临时目录，避免测试污染工作区
            ns["STRATEGY_PATH"] = folder / "daily_strategy.json"

            ti = _FakeTaskInstance()
            context = {
                "ti": ti,
                "params": {
                    "prefer_network": False,
                    "raw_path": folder / "raw.csv",
                    "processed_path": folder / "processed.csv",
                    "metadata_path": folder / "metadata.json",
                },
            }

            pipeline = ns["task_run_pipeline"](**context)
            ti.xcom_push("run_pipeline", pipeline)
            strategy = ns["task_score_and_optimize"](**context)
            ti.xcom_push("score_and_optimize", strategy)
            persisted = ns["task_persist_strategy"](**context)

            payload = json.loads(
                Path(persisted["strategy_path"]).read_text(encoding="utf-8")
            )

        self.assertEqual(pipeline["vegetables"], 15)
        self.assertTrue(pipeline["used_fallback"], "断网时应回退本地 CSV")
        self.assertEqual(strategy["plants_ranked"], 15)
        self.assertTrue(strategy["all_constraints_met"])
        self.assertEqual(strategy["failed_constraints"], [])
        self.assertEqual(strategy["score_column"], "apocalypse_index")
        self.assertGreaterEqual(len(strategy["combination"]), 1)

        self.assertEqual(payload["pipeline"]["rows"], pipeline["rows"])
        self.assertEqual(payload["strategy"]["combination"], strategy["combination"])

    def test_smoke_entrypoint_runs_without_airflow_installed(self) -> None:
        """`python airflow/dags/pvz_dag.py` 在未安装 Airflow 的环境下必须能跑通。

        文件顶部对 Airflow 导入做了兜底。若哪天有人把它改回无条件导入，
        这个用例会立刻失败——否则 README 里"不装 Airflow 也能验证链路"
        的说法就会变成空话（曾真实发生过一次）。
        """
        result = subprocess.run(
            [sys.executable, str(DAG_PATH)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )

        self.assertEqual(result.returncode, 0, f"退出码非 0\nstderr:\n{result.stderr}")
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertIn("[run_pipeline]", result.stdout)
        self.assertIn("[score_and_optimize]", result.stdout)
        self.assertIn("[persist_strategy]", result.stdout)


if __name__ == "__main__":
    unittest.main()
