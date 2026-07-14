"""PvZ-inspired Streamlit dashboard for the V2.0 recommendation system."""

from __future__ import annotations

from html import escape
import inspect
from pathlib import Path

import streamlit as st

from src.dashboard import (
    PLANT_EMOJI,
    ZOMBIE_MODES,
    build_dashboard_model,
    get_price_trend,
)
from src.user_data import prepare_uploaded_price_data


ROOT = Path(__file__).resolve().parent
STYLE_PATH = ROOT / "assets" / "style.css"
TEMPLATE_PATH = ROOT / "data" / "templates" / "regional_prices_template.csv"
ANALYSIS_MODEL_KEY = "analysis_model"
ANALYSIS_PARAMS_KEY = "analysis_params"
ANALYSIS_ERROR_KEY = "analysis_error"


@st.cache_data(show_spinner=False)
def get_dashboard_model(mode: str, sun: int, cells: int) -> dict:
    """Cache deterministic model results by the visible UI parameters."""

    return build_dashboard_model(mode, sun, cells)


@st.cache_data(show_spinner=False)
def get_uploaded_dashboard_model(
    mode: str,
    sun: int,
    cells: int,
    region_name: str,
    csv_content: bytes,
) -> dict:
    """Prepare one uploaded region and calculate its recommendation."""

    prices = prepare_uploaded_price_data(csv_content, region_name=region_name)
    return build_dashboard_model(mode, sun, cells, price_data=prices)


def load_styles() -> None:
    """Load the copyright-safe CSS theme from the project asset directory."""

    st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def stretch_width(component: object) -> dict[str, object]:
    """Use the current width API while retaining Streamlit 1.28 compatibility."""

    parameters = inspect.signature(component).parameters
    return {"width": "stretch"} if "width" in parameters else {"use_container_width": True}


def build_submitted_dashboard_model(
    zombie_mode: str,
    available_sun: int,
    available_cells: int,
    region_name: str,
    uploaded_file: object | None,
) -> dict:
    """Calculate a model only for an explicit form submission."""

    if uploaded_file is None:
        return get_dashboard_model(zombie_mode, available_sun, available_cells)
    return get_uploaded_dashboard_model(
        zombie_mode,
        available_sun,
        available_cells,
        region_name,
        uploaded_file.getvalue(),
    )


def render_sidebar_status() -> None:
    """Show whether the submitted configuration has a usable result."""

    if st.session_state.get(ANALYSIS_ERROR_KEY):
        css_class = "is-error"
        icon = "!"
        title = "配置需要修正"
        copy = "已保留上一次成功结果；修正后请重新分析。"
    elif st.session_state.get(ANALYSIS_MODEL_KEY) is not None:
        css_class = "is-complete"
        icon = "✓"
        title = "分析完成"
        copy = "当前结果对应最近一次提交的作战配置。"
    else:
        css_class = "is-waiting"
        icon = "…"
        title = "等待分析"
        copy = "设置参数后点击“开始分析”。"

    st.markdown(
        f"""
        <div class="analysis-status {css_class}" role="status">
          <span class="analysis-status-icon">{icon}</span>
          <span><strong>{title}</strong><small>{copy}</small></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_waiting_state() -> None:
    """Render the intentional pre-analysis state instead of fake results."""

    st.markdown(
        """
        <section class="waiting-panel" role="status" aria-label="等待作战配置">
          <div class="waiting-icon" aria-hidden="true">🌱</div>
          <div>
            <span class="waiting-kicker">AWAITING ORDERS</span>
            <h1>等待作战配置</h1>
            <p>请在左侧设置僵尸模式、阳光和草坪格子，然后点击“🚀 开始分析”。</p>
            <div class="waiting-steps">
              <span>1 · 设置参数</span>
              <span>2 · 可选上传菜价</span>
              <span>3 · 提交分析</span>
            </div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_hero(model: dict, available_sun: int, available_cells: int) -> None:
    mode = model["mode"]
    st.markdown(
        f"""
        <section class="hero-panel">
          <div class="hero-copy">
            <div class="eyebrow">🌱 PVZ ECONOMY ENGINE · V2.0</div>
            <h1>末日菜园作战室</h1>
            <p>把真实菜价、植物战力与有限资源装进同一块草坪。</p>
            <div class="hero-badges">
              <span>{escape(mode['icon'])} {escape(model['zombie_mode'])}</span>
              <span>📡 {escape(model['data_source'])}</span>
              <span>🗓️ 数据截至 {model['latest_date'].strftime('%Y-%m-%d')}</span>
            </div>
          </div>
          <div class="sun-counter" aria-label="阳光计数器">
            <span class="sun-icon">☀️</span>
            <span class="sun-value">{available_sun}</span>
            <span class="sun-label">可用阳光</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    result = model["result"]
    metrics = [
        ("☀️", "阳光消耗", f"{result['total_sun_cost']} / {available_sun}"),
        ("▦", "草坪格子", f"{result['total_plants']} / {available_cells}"),
        ("🏆", model["score_label"], f"{result['total_score']:.2f}"),
        ("⚙️", "求解方式", "整数规划" if result["method"] == "pulp" else "贪心兜底"),
    ]
    metric_html = "".join(
        f'<div class="battle-metric">'
        f'<span class="metric-icon">{icon}</span>'
        f'<span class="metric-label">{escape(label)}</span>'
        f'<strong>{escape(value)}</strong>'
        f'</div>'
        for icon, label, value in metrics
    )
    st.markdown(f'<div class="battle-metric-grid">{metric_html}</div>', unsafe_allow_html=True)


def render_constraint_bar(result: dict) -> None:
    labels = {
        "sun_limit": "阳光预算",
        "cell_limit": "格子上限",
        "has_attack": "攻击植物",
        "has_defense_or_control": "防御/控制",
    }
    chips = "".join(
        f'<span class="constraint-chip {"is-ok" if passed else "is-bad"}">'
        f'{"✓" if passed else "!"} {labels[key]}</span>'
        for key, passed in result["constraint_checks"].items()
    )
    st.markdown(f'<div class="constraint-row">{chips}</div>', unsafe_allow_html=True)


def render_seed_cards(model: dict) -> None:
    ranking = model["ranking"].set_index("name")
    cards = []
    for item in model["result"]["combination"]:
        row = ranking.loc[item["name"]]
        emoji = PLANT_EMOJI.get(item["name"], "🌱")
        cards.append(
            f'<article class="seed-card">'
            f'<div class="seed-card-top">'
            f'<span class="sun-cost">☀ {item["unit_sun_cost"]}</span>'
            f'<span class="seed-count">× {item["quantity"]}</span>'
            f'</div>'
            f'<div class="plant-emoji" aria-hidden="true">{emoji}</div>'
            f'<h3>{escape(item["name"])}</h3>'
            f'<p class="plant-role">{escape(str(row["role"]))}</p>'
            f'<div class="seed-stats">'
            f'<span>⚔ {int(row["attack"])}</span>'
            f'<span>🛡 {int(row["defense"])}</span>'
            f'<span>🌀 {int(row["control"])}</span>'
            f'</div>'
            f'<div class="score-strip">单株指数 '
            f'<strong>{item["unit_score"]:.2f}</strong></div>'
            f'</article>'
        )
    st.markdown(f'<div class="seed-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_lawn(model: dict, available_cells: int) -> None:
    slots: list[tuple[str, str]] = []
    for item in model["result"]["combination"]:
        emoji = PLANT_EMOJI.get(item["name"], "🌱")
        slots.extend([(emoji, item["name"])] * int(item["quantity"]))
    slots = slots[:available_cells]
    slots.extend([("", "空格")] * (available_cells - len(slots)))

    cells = []
    for index, (emoji, name) in enumerate(slots, start=1):
        if emoji:
            cells.append(
                f'<div class="lawn-cell occupied" title="{escape(name)}">'
                f'<span>{emoji}</span><small>{escape(name)}</small></div>'
            )
        else:
            cells.append(
                f'<div class="lawn-cell empty" title="空格 {index}"><span>＋</span></div>'
            )
    st.markdown(f'<div class="lawn-board">{"".join(cells)}</div>', unsafe_allow_html=True)


def render_reasons(model: dict) -> None:
    reason_cards = []
    for reason in model["reasons"]:
        reason_cards.append(
            f'<article class="reason-card">'
            f'<div class="reason-icon">{reason["emoji"]}</div>'
            f'<div><div class="reason-title">'
            f'<strong>{escape(reason["name"])} × {reason["quantity"]}</strong>'
            f'<span>{escape(str(reason["role"]))}</span>'
            f'</div><p>{escape(reason["text"])}</p></div>'
            f'</article>'
        )
    st.markdown(f'<div class="reason-grid">{"".join(reason_cards)}</div>', unsafe_allow_html=True)


def section_header(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="section-heading">
          <span class="section-kicker">{escape(kicker)}</span>
          <h2>{escape(title)}</h2>
          <p>{escape(copy)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="末日菜园作战室",
        page_icon="🌻",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    load_styles()

    with st.sidebar:
        st.markdown('<div class="sidebar-brand">🌻<strong>作战配置</strong></div>', unsafe_allow_html=True)
        with st.form("analysis_form"):
            zombie_mode = st.selectbox(
                "僵尸模式",
                options=list(ZOMBIE_MODES),
                help="提交分析后，敌情会调整五项战斗价值权重。",
            )
            available_sun = st.slider("☀️ 可用阳光", 50, 500, 150, 25)
            available_cells = st.slider("🌱 草坪格子", 5, 45, 20, 5)
            st.markdown('<div class="form-section-label">📍 地区菜价（可选）</div>', unsafe_allow_html=True)
            region_name = st.text_input(
                "地区名称",
                value="我的地区",
                help="例如：上海浦东、成都双流。名称只用于标记数据来源。",
            )
            uploaded_file = st.file_uploader(
                "上传地区菜价 CSV",
                type=["csv"],
                help="支持 date/name/price/unit 或对应中文列名；价格单位支持元/kg、元/斤。",
            )
            st.caption("表单内容只会在点击按钮后生效。")
            submitted = st.form_submit_button(
                "🚀 开始分析",
                type="primary",
                **stretch_width(st.form_submit_button),
            )

        if submitted:
            try:
                with st.spinner("正在计算末日种植方案..."):
                    submitted_model = build_submitted_dashboard_model(
                        zombie_mode,
                        available_sun,
                        available_cells,
                        region_name,
                        uploaded_file,
                    )
            except ValueError as exc:
                st.session_state[ANALYSIS_ERROR_KEY] = str(exc)
            else:
                st.session_state[ANALYSIS_MODEL_KEY] = submitted_model
                st.session_state[ANALYSIS_PARAMS_KEY] = {
                    "zombie_mode": zombie_mode,
                    "available_sun": available_sun,
                    "available_cells": available_cells,
                    "region_name": region_name,
                    "uses_uploaded_csv": uploaded_file is not None,
                }
                st.session_state[ANALYSIS_ERROR_KEY] = None

        render_sidebar_status()
        st.download_button(
            "⬇️ 下载 CSV 模板",
            data=TEMPLATE_PATH.read_bytes(),
            file_name="regional_prices_template.csv",
            mime="text/csv",
            **stretch_width(st.download_button),
        )
        st.markdown(
            """
            <div class="sidebar-note">
              <strong>离线可运行</strong>
              <span>不上传时使用北京示例；上传后按你的地区菜价重新分析。</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("本页面只使用 emoji 与原创 CSS，不含官方游戏素材。")

    analysis_error = st.session_state.get(ANALYSIS_ERROR_KEY)
    model = st.session_state.get(ANALYSIS_MODEL_KEY)
    if analysis_error:
        st.error(f"地区菜价无法分析：{analysis_error}")
        st.info("可以先下载侧栏 CSV 模板，保留表头后替换成当地菜价。")

    if model is None:
        render_waiting_state()
        return

    committed_params = st.session_state[ANALYSIS_PARAMS_KEY]
    available_sun = int(committed_params["available_sun"])
    available_cells = int(committed_params["available_cells"])
    result = model["result"]

    render_hero(model, available_sun, available_cells)
    st.markdown(
        f'<div class="model-notice">🧪 <strong>{escape(model["score_label"])}</strong> · '
        f'{escape(model["score_notice"])}</div>',
        unsafe_allow_html=True,
    )
    render_constraint_bar(result)

    coverage = model["coverage"]
    if coverage["excluded_plants"]:
        excluded = "、".join(coverage["excluded_plants"])
        st.info(
            f"本次菜价关联到 {coverage['matched_plants']} / "
            f"{coverage['total_plants']} 种植物；缺少对应菜价的植物暂不参赛：{excluded}。"
        )

    if not result["all_constraints_met"]:
        st.error(result["recommendation_reason"])
        return

    section_header(
        "SEED DECK",
        "植物推荐卡片",
        "每张种子卡展示成本、数量、定位与本轮末日性价比指数。",
    )
    render_seed_cards(model)

    section_header(
        "LAWN PLAN",
        "草坪网格布局",
        "五列草坪模拟有限种植空间；空格会随着资源参数自动变化。",
    )
    render_lawn(model, available_cells)

    section_header(
        "MARKET INTEL",
        "菜价趋势与推荐排行",
        "菜价经过统一清洗和 30 日特征计算；僵尸模式变化会触发重新评分。",
    )
    chart_left, chart_right = st.columns([1.15, 1])
    vegetables = model["ranking"]["vegetable_name"].drop_duplicates().tolist()
    with chart_left:
        selected_vegetable = st.selectbox("查看蔬菜价格", vegetables)
        trend = get_price_trend(model["prices"], selected_vegetable)
        st.line_chart(
            trend.set_index("date")[["price"]],
            height=310,
            **stretch_width(st.line_chart),
        )
        st.caption(f"{selected_vegetable} · 单位：元/kg · 来源：{model['data_source']}")
    with chart_right:
        top_ranking = (
            model["ranking"]
            .head(10)
            .set_index("name")[["apocalypse_index"]]
            .rename(columns={"apocalypse_index": "末日性价比指数"})
        )
        st.bar_chart(top_ranking, height=310, **stretch_width(st.bar_chart))
        st.caption("Top 10 末日性价比指数；僵尸模式变化后自动重排。")

    section_header(
        "WHY THIS TEAM",
        "推荐理由解释",
        result["recommendation_reason"],
    )
    render_reasons(model)

    with st.expander("查看完整植物排行与模型状态"):
        table = model["ranking"][
            [
                "rank",
                "name",
                "vegetable_name",
                "role",
                "sun_cost",
                "latest_price",
                "battle_value",
                "price_undervaluation",
                "stability_coefficient",
                "apocalypse_index",
                "recommendation_reason",
            ]
        ].rename(
            columns={
                "rank": "排名",
                "name": "植物",
                "vegetable_name": "映射蔬菜",
                "role": "定位",
                "sun_cost": "阳光成本",
                "latest_price": "最新菜价(元/kg)",
                "battle_value": "战斗价值",
                "price_undervaluation": "价格低估系数",
                "stability_coefficient": "稳定性系数",
                "apocalypse_index": "末日性价比指数",
                "recommendation_reason": "评分理由",
            }
        )
        st.dataframe(table, hide_index=True, **stretch_width(st.dataframe))
        st.json(
            {
                "求解状态": result["status"],
                "约束检查": result["constraint_checks"],
                "评分权重": model["weights"],
            }
        )

    st.markdown(
        """
        <footer class="page-footer">
          <span>🌱 PvZ Economy Engine V2.0</span>
          <span>数据分析与运筹优化练习 · 非官方游戏项目</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
