"""Batch 6 tests for the Streamlit dashboard model and app reruns."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard import ZOMBIE_MODES, build_dashboard_model, get_price_trend
from src.user_data import prepare_uploaded_price_data


class DashboardModelTests(unittest.TestCase):
    def test_dashboard_model_contains_all_required_sections_data(self) -> None:
        model = build_dashboard_model("均衡巡逻", 150, 20)
        self.assertEqual(len(model["ranking"]), 15)
        self.assertFalse(model["prices"].empty)
        self.assertTrue(model["result"]["all_constraints_met"])
        self.assertTrue(model["result"]["combination"])
        self.assertEqual(len(model["reasons"]), len(model["result"]["combination"]))
        self.assertEqual(model["result"]["score_column"], "apocalypse_index")
        self.assertEqual(model["score_label"], "末日性价比指数")

    def test_every_zombie_mode_can_refresh_a_recommendation(self) -> None:
        scores = []
        for mode in ZOMBIE_MODES:
            with self.subTest(mode=mode):
                model = build_dashboard_model(mode, 200, 20)
                self.assertTrue(model["result"]["strategy"])
                self.assertTrue(model["result"]["all_constraints_met"])
                scores.append(model["result"]["total_score"])
        self.assertGreater(len(set(scores)), 1)

    def test_price_trend_is_ordered_and_non_empty(self) -> None:
        model = build_dashboard_model("尸潮来袭", 150, 20)
        vegetable = model["ranking"].iloc[0]["vegetable_name"]
        trend = get_price_trend(model["prices"], vegetable)
        self.assertFalse(trend.empty)
        self.assertTrue(trend["date"].is_monotonic_increasing)

    def test_uploaded_region_can_score_partial_mapping(self) -> None:
        content = (ROOT / "data" / "templates" / "regional_prices_template.csv").read_bytes()
        prices = prepare_uploaded_price_data(content, region_name="测试地区")
        model = build_dashboard_model(
            "均衡巡逻",
            150,
            20,
            price_data=prices,
        )
        self.assertIn("用户上传 · 测试地区", model["data_source"])
        self.assertGreaterEqual(model["coverage"]["matched_plants"], 2)
        self.assertLess(model["coverage"]["matched_plants"], 15)
        self.assertTrue(model["result"]["all_constraints_met"])


class StreamlitAppTests(unittest.TestCase):
    def test_app_source_declares_required_dashboard_sections(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        required_labels = (
            "阳光计数器",
            "僵尸模式",
            "植物推荐卡片",
            "草坪网格布局",
            "菜价趋势与推荐排行",
            "推荐理由解释",
            "上传地区菜价 CSV",
            "下载 CSV 模板",
        )
        for label in required_labels:
            with self.subTest(label=label):
                self.assertIn(label, source)

    def test_app_starts_and_refreshes_after_parameter_change(self) -> None:
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:  # pragma: no cover - old supported Streamlit releases
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        app.sidebar.selectbox[0].select("尸潮来袭")
        app.sidebar.slider[0].set_value(200)
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
