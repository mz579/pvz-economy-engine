"""Batch 6 tests for the Streamlit dashboard model and app reruns."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys
import tempfile
import unittest
from zipfile import ZipFile

import pandas as pd


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
        lane_defense = model["result"]["lane_defense"]
        self.assertEqual(lane_defense["lanes_count"], 5)
        self.assertEqual(len(lane_defense["lanes"]), 5)
        self.assertIn(lane_defense["weakest_lane"], range(1, 6))
        self.assertEqual(model["scenario"], "day")
        self.assertEqual(model["result"]["scenario"], "day")
        self.assertEqual(model["score_label"], "末日性价比指数")
        self.assertEqual(model["price_unit"], "元/kg")
        comparison = model["candidate_comparison"]
        self.assertEqual(len(comparison), 15)
        self.assertTrue(comparison["has_price"].all())
        self.assertTrue(
            comparison["apocalypse_index"].is_monotonic_decreasing
        )
        selected_names = set(model["result"]["strategy"])
        self.assertSetEqual(
            set(comparison.loc[comparison["selected"], "name"]),
            selected_names,
        )

    def test_every_zombie_mode_can_refresh_a_recommendation(self) -> None:
        # V3 selection is driven by plant attributes, so the same grid/sun can
        # yield the same roster across modes; the mode-specific ranking must
        # still change and every recommendation must remain valid.
        ranking_vectors = []
        for mode in ZOMBIE_MODES:
            with self.subTest(mode=mode):
                model = build_dashboard_model(mode, 200, 20)
                self.assertTrue(model["result"]["strategy"])
                self.assertTrue(model["result"]["all_constraints_met"])
                self.assertEqual(model["result"]["per_plant_limit"], 6)
                for item in model["result"]["combination"]:
                    bound = (
                        20
                        if float(item["unit_sun_cost"]) == 0
                        else model["result"]["per_plant_limit"]
                    )
                    self.assertLessEqual(int(item["quantity"]), bound)
                self.assertGreater(model["result"]["total_score"], 0)
                ranking_vectors.append(
                    tuple(
                        round(float(value), 8)
                        for value in model["ranking"]["apocalypse_index"]
                    )
                )
        self.assertGreater(len(set(ranking_vectors)), 1)

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
        self.assertTrue(model["result"]["constraint_checks"]["per_plant_limit"])
        comparison = model["candidate_comparison"]
        unmapped = comparison.loc[~comparison["has_price"]]
        self.assertFalse(unmapped.empty)
        self.assertTrue(unmapped["current_price"].isna().all())
        self.assertTrue(unmapped["historical_mean"].isna().all())
        self.assertTrue(unmapped["apocalypse_index"].isna().all())
        self.assertTrue(unmapped["price_unit"].isna().all())

    def test_display_lawn_matches_capacity_and_recommendation_quantities(self) -> None:
        from app import build_lawn_slots

        available_cells = 20
        model = build_dashboard_model("均衡巡逻", 150, available_cells)
        slots = build_lawn_slots(model, available_cells)
        occupied = [slot for slot in slots if slot["occupied"]]

        self.assertEqual(len(slots), available_cells)
        self.assertEqual(len(occupied), model["result"]["total_plants"])
        self.assertEqual(
            len([slot for slot in slots if not slot["occupied"]]),
            model["result"]["unused_cells"],
        )
        self.assertEqual(
            Counter(str(slot["name"]) for slot in occupied),
            Counter(
                {
                    item["name"]: int(item["quantity"])
                    for item in model["result"]["combination"]
                }
            ),
        )

    def test_default_recommendation_caps_paid_plants_and_fills_with_free_plants(self) -> None:
        model = build_dashboard_model("均衡巡逻", 150, 20)
        result = model["result"]

        self.assertEqual(result["per_plant_limit"], 6)
        self.assertEqual(result["max_plant_share"], 0.30)
        # Default day scenario: mushrooms sleep, so the roster contains only
        # awaken plants; there is no free attacker to fill the unused cells.
        self.assertDictEqual(
            result["strategy"],
            {"向日葵": 1, "土豆雷": 3, "灯笼草": 1},
        )
        self.assertFalse(set(result["strategy"]) & {"小喷菇", "阳光菇", "大喷菇"})
        for item in result["combination"]:
            bound = 20 if float(item["unit_sun_cost"]) == 0 else 6
            self.assertLessEqual(int(item["quantity"]), bound)
        self.assertEqual(result["total_sun_cost"], 150)
        self.assertEqual(result["total_plants"], 5)
        self.assertEqual(result["unused_cells"], 15)
        self.assertIn("0 阳光攻击植物", result["unused_cells_reason"])
        self.assertAlmostEqual(
            result["total_score"],
            sum(item["subtotal_score"] for item in result["combination"]),
            delta=1e-3,
        )
        self.assertGreater(result["objective_value"], 0)
        self.assertEqual(result["method"], "v3-simulation")
        self.assertEqual(result["status"], "Feasible (v3 simulation)")
        self.assertEqual(model["concentration_policy"]["per_plant_limit"], 6)
        self.assertTrue(model["concentration_policy"]["is_v2_assumption"])

    def test_night_scenario_allows_mushrooms_and_removes_sky_sun(self) -> None:
        model = build_dashboard_model(
            "均衡巡逻",
            150,
            20,
            scenario="night",
        )
        result = model["result"]

        self.assertEqual(model["scenario"], "night")
        self.assertEqual(result["scenario"], "night")
        selected = set(result["strategy"])
        self.assertTrue(selected & {"小喷菇", "阳光菇", "大喷菇"})
        self.assertGreater(result["strategy"]["小喷菇"], 6)
        self.assertEqual(result["total_plants"], 20)
        self.assertEqual(result["unused_cells"], 0)
        self.assertEqual(result["sun_economy"]["sky_sun_per_sec"], 0.0)
        self.assertEqual(result["sun_economy"]["sky_sun_over_horizon"], 0.0)

    def test_chart_state_handles_empty_single_constant_and_regular_data(self) -> None:
        from app import chart_data_state

        self.assertEqual(
            chart_data_state(pd.DataFrame(columns=["price"]), ["price"]),
            "empty",
        )
        self.assertEqual(
            chart_data_state(pd.DataFrame({"price": [3.2]}), ["price"]),
            "single",
        )
        self.assertEqual(
            chart_data_state(pd.DataFrame({"price": [3.2, 3.2]}), ["price"]),
            "single",
        )
        self.assertEqual(
            chart_data_state(pd.DataFrame({"price": [3.2, 3.4]}), ["price"]),
            "chart",
        )


class StreamlitAppTests(unittest.TestCase):
    @staticmethod
    def load_app_test():
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:  # pragma: no cover - old supported Streamlit releases
            return None
        return AppTest.from_file(str(ROOT / "app.py"))

    @staticmethod
    def rendered_html(app) -> str:
        return "\n".join(item.value for item in app.markdown)

    def test_app_source_declares_required_dashboard_sections(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        required_labels = (
            "僵尸模式",
            "场景",
            "本轮建议种植",
            "全部候选植物对比",
            "价格与评分",
            "作战属性",
            "推荐原因",
            "市场证据",
            "当前价格",
            "为什么入选",
            "阵容展示布局",
            "非优化器计算出的最优坐标",
            "模型说明与技术细节",
            "评分与权重",
            "完整植物排名",
            "优化与映射",
            "调试信息",
            "相对比较指数",
            "每种植物最多占草坪容量的",
            "空格不代表错误或不可行",
            "上传地区菜价 CSV",
            "下载 CSV 模板",
            "🚀 开始分析",
            "等待作战配置",
        )
        for label in required_labels:
            with self.subTest(label=label):
                self.assertIn(label, source)

        ordered_calls = (
            "render_hero(model)",
            "render_recommendation_summary(model, available_sun, available_cells)",
            "render_reasons(model)",
            "render_market_section(model)",
            "render_candidate_comparison(model)",
            "render_technical_details(model)",
        )
        positions = [source.index(call, source.index("def main()")) for call in ordered_calls]
        self.assertEqual(positions, sorted(positions))
        expander_position = source.index('with st.expander("模型说明与技术细节")')
        for technical_label in ("评分与权重", "完整植物排名", "优化与映射", "调试信息"):
            self.assertGreater(source.index(technical_label), expander_position)

    def test_app_waits_for_explicit_analysis(self) -> None:
        app_test = self.load_app_test()
        if app_test is None:
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        app = app_test.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.sidebar.button), 1)
        self.assertEqual(app.sidebar.button[0].label, "🚀 开始分析")
        self.assertEqual(app.sidebar.button[0].proto.type, "primary")
        self.assertNotIn("analysis_model", app.session_state)
        self.assertTrue(any("等待作战配置" in item.value for item in app.markdown))

        app.sidebar.button[0].click()
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertIn("analysis_model", app.session_state)
        self.assertEqual(app.session_state["analysis_params"]["available_sun"], 150)
        self.assertEqual(app.session_state["analysis_params"]["available_cells"], 20)
        self.assertEqual(app.session_state["analysis_params"]["scenario"], "day")
        self.assertFalse(app.session_state["analysis_params"]["uses_uploaded_csv"])
        html = self.rendered_html(app)
        self.assertIn("terminal-header", html)
        self.assertIn("recommendation-summary is-success", html)
        self.assertIn("resource-strip", html)
        self.assertIn("deployment-stage", html)
        self.assertIn("roster-sheet", html)
        self.assertIn("lawn-panel", html)
        self.assertIn("阵容展示布局", html)
        self.assertIn("非优化器计算出的最优坐标", html)
        self.assertIn("✓ 分析完成", html)
        self.assertIn("阳光消耗", html)
        self.assertIn("草坪占用", html)
        self.assertIn("相对比较指数", html)
        self.assertIn("每种植物最多占草坪容量的 30%，本轮最多 6 株", html)
        self.assertIn("未使用位置会保留为空格，不表示错误或不可行", html)
        # Default day scenario has no free mushroom filler, so 15 cells stay
        # empty and the summary states that explicitly.
        self.assertIn("本轮保留 15 个空格", html)
        self.assertIn("当前场景", html)
        self.assertIn("☀️ 白天", html)
        self.assertIn("reason-points", html)
        self.assertIn("当前价格", html)
        self.assertIn("为什么入选", html)
        self.assertIn("market-method-note", html)
        self.assertIn("元/斤", html)
        for item in app.session_state["analysis_model"]["result"]["combination"]:
            with self.subTest(plant=item["name"]):
                self.assertIn(item["name"], html)
                self.assertIn(f"× {item['quantity']}", html)
                row = app.session_state["analysis_model"]["ranking"].set_index("name").loc[item["name"]]
                self.assertIn(row["vegetable_name"], html)
                self.assertIn(
                    f"{row['current_price']:.2f} {app.session_state['analysis_model']['price_unit']}",
                    html,
                )
                self.assertIn(f"{row['apocalypse_index']:.4f}", html)
                self.assertEqual(
                    html.count(f'data-plant="{item["name"]}"'),
                    int(item["quantity"]),
                )
        self.assertEqual(html.count('class="lawn-cell '), 20)
        self.assertEqual(
            html.count('class="lawn-cell is-occupied"'),
            app.session_state["analysis_model"]["result"]["total_plants"],
        )
        self.assertEqual(
            html.count('class="lawn-cell is-empty"'),
            app.session_state["analysis_model"]["result"]["unused_cells"],
        )
        self.assertEqual(len(app.expander), 1)
        self.assertEqual(app.expander[0].label, "模型说明与技术细节")

    def test_unsubmitted_form_changes_keep_last_result(self) -> None:
        app_test = self.load_app_test()
        if app_test is None:
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        app = app_test.run(timeout=30)
        app.sidebar.button[0].click()
        app.run(timeout=30)
        original_score = app.session_state["analysis_model"]["result"]["total_score"]

        # A change inside st.form is only staged: rerunning without submitting
        # must not commit it, so the slider keeps the last submitted value and
        # the previous analysis result stays untouched.
        app.sidebar.slider[0].set_value(200)
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.sidebar.slider[0].value, 150)
        self.assertEqual(app.session_state["analysis_params"]["available_sun"], 150)
        self.assertEqual(
            app.session_state["analysis_model"]["result"]["total_score"],
            original_score,
        )

        # Submitting the form together with the staged value commits it.
        app.sidebar.slider[0].set_value(200)
        app.sidebar.button[0].click()
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["analysis_params"]["available_sun"], 200)

    def test_incomplete_portable_package_hides_python_traceback(self) -> None:
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:  # pragma: no cover - old supported Streamlit releases
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        from scripts.build_release import build_release

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = build_release("v2.1.2-damaged", root / "dist")
            with ZipFile(archive) as package:
                package.extractall(root / "extract")
            package_root = root / "extract" / "pvz-economy-engine-v2.1.2-damaged"
            (package_root / "data" / "plants.csv").unlink()

            app = AppTest.from_file(str(package_root / "app.py")).run(timeout=30)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertIn("安装包不完整，请重新下载", app.error[0].value)
        rendered = self.rendered_html(app)
        self.assertNotIn("Traceback", rendered)
        self.assertNotIn("FileNotFoundError", rendered)

    def test_invalid_csv_error_only_appears_after_submit(self) -> None:
        app_test = self.load_app_test()
        if app_test is None:
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        app = app_test.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("analysis_error", app.session_state)
        self.assertEqual(len(app.error), 0)

        # A file staged inside st.form is only registered when the form is
        # submitted, so stage the invalid CSV and submit it in the same run.
        app.sidebar.file_uploader[0].upload(
            "invalid.csv",
            b"unexpected\nvalue\n",
            "text/csv",
        )
        app.sidebar.button[0].click()
        app.run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.session_state["analysis_error"])
        self.assertNotIn("analysis_model", app.session_state)
        self.assertEqual(len(app.error), 1)

    def test_partial_user_csv_has_success_and_coverage_states(self) -> None:
        app_test = self.load_app_test()
        if app_test is None:
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        content = (ROOT / "data" / "templates" / "regional_prices_template.csv").read_bytes()
        app = app_test.run(timeout=30)
        # Upload and submit in one run: a file staged inside st.form only
        # registers when the form is submitted.
        app.sidebar.file_uploader[0].upload("region.csv", content, "text/csv")
        app.sidebar.button[0].click()
        app.run(timeout=30)

        self.assertEqual(len(app.exception), 0)
        model = app.session_state["analysis_model"]
        self.assertTrue(model["result"]["all_constraints_met"])
        self.assertTrue(model["coverage"]["excluded_plants"])
        html = self.rendered_html(app)
        self.assertIn("recommendation-summary is-success", html)
        self.assertIn("部分菜价已成功映射", html)
        self.assertIn("用户上传", model["data_source"])

    def test_visual_tokens_keep_sidebar_text_at_wcag_aa(self) -> None:
        def channel(value: int) -> float:
            normalized = value / 255
            return (
                normalized / 12.92
                if normalized <= 0.04045
                else ((normalized + 0.055) / 1.055) ** 2.4
            )

        def luminance(hex_color: str) -> float:
            red, green, blue = (
                int(hex_color[index : index + 2], 16)
                for index in (1, 3, 5)
            )
            return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)

        def contrast(foreground: str, background: str) -> float:
            light, dark = sorted(
                (luminance(foreground), luminance(background)), reverse=True
            )
            return (light + 0.05) / (dark + 0.05)

        style = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertNotRegex(style, re.compile(r"letter-spacing\s*:\s*-"))
        self.assertIn("@media (max-width: 620px)", style)
        self.assertIn("overflow-x: hidden", style)
        self.assertIn(".chart-state", style)
        self.assertGreaterEqual(contrast("#F1F4DF", "#0B1811"), 4.5)
        self.assertGreaterEqual(contrast("#A9B9A8", "#0B1811"), 4.5)

    def test_readme_documents_current_ui_and_model_boundaries(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for statement in (
            "🚀 开始分析",
            "元/斤",
            "乘以 2",
            "不是百分制、收益率或成功概率",
            "展示布局",
            "用户 CSV",
            "离线 fallback",
            "ceil(格子数 × 30%)",
            "优化结果允许保留空格",
            "阳光经济 · 攻防 · 车道 · 昼夜",
            "0 阳光植物不受此限",
            "小喷菇 ×14",
            "昼夜（场景）",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, readme)

    def test_documented_screenshots_match_validated_viewports(self) -> None:
        def png_dimensions(path: Path) -> tuple[int, int]:
            content = path.read_bytes()
            self.assertEqual(content[:8], b"\x89PNG\r\n\x1a\n")
            return (
                int.from_bytes(content[16:20], "big"),
                int.from_bytes(content[20:24], "big"),
            )

        screenshot_dir = ROOT / "docs" / "screenshots"
        self.assertEqual(
            png_dimensions(screenshot_dir / "dashboard.png"),
            (1280, 720),
        )
        self.assertEqual(
            png_dimensions(screenshot_dir / "dashboard-mobile.png"),
            (390, 844),
        )

    def test_infeasible_user_csv_has_independent_error_state(self) -> None:
        app_test = self.load_app_test()
        if app_test is None:
            self.skipTest("当前 Streamlit 版本不包含 AppTest")

        content = (
            "date,name,price,unit\n"
            "2026-07-07,豌豆,4.00,元/kg\n"
            "2026-07-08,豌豆,4.10,元/kg\n"
            "2026-07-09,豌豆,4.05,元/kg\n"
            "2026-07-10,豌豆,4.20,元/kg\n"
            "2026-07-11,豌豆,4.15,元/kg\n"
            "2026-07-12,豌豆,4.08,元/kg\n"
            "2026-07-13,豌豆,4.12,元/kg\n"
        ).encode("utf-8")
        app = app_test.run(timeout=30)
        # Upload and submit in one run: a file staged inside st.form only
        # registers when the form is submitted.
        app.sidebar.file_uploader[0].upload("attack-only.csv", content, "text/csv")
        app.sidebar.button[0].click()
        app.run(timeout=30)

        self.assertEqual(len(app.exception), 0)
        model = app.session_state["analysis_model"]
        self.assertFalse(model["result"]["all_constraints_met"])
        self.assertFalse(model["result"]["combination"])
        html = self.rendered_html(app)
        self.assertIn("recommendation-summary is-infeasible", html)
        self.assertIn("本轮暂无可行种植方案", html)
        self.assertIn("方案不可行", html)
        self.assertIn("部分菜价已成功映射", html)


if __name__ == "__main__":
    unittest.main()
