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


ROOT = Path(__file__).resolve().parent
STYLE_PATH = ROOT / "assets" / "style.css"


@st.cache_data(show_spinner=False)
def get_dashboard_model(mode: str, sun: int, cells: int) -> dict:
    """Cache deterministic model results by the visible UI parameters."""

    return build_dashboard_model(mode, sun, cells)


def load_styles() -> None:
    """Load the copyright-safe CSS theme from the project asset directory."""

    st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def stretch_width(component: object) -> dict[str, object]:
    """Use the current width API while retaining Streamlit 1.28 compatibility."""

    parameters = inspect.signature(component).parameters
    return {"width": "stretch"} if "width" in parameters else {"use_container_width": True}


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
        f"""
        <div class="battle-metric">
          <span class="metric-icon">{icon}</span>
          <span class="metric-label">{escape(label)}</span>
          <strong>{escape(value)}</strong>
        </div>
        """
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
            f"""
            <article class="seed-card">
              <div class="seed-card-top">
                <span class="sun-cost">☀ {item['unit_sun_cost']}</span>
                <span class="seed-count">× {item['quantity']}</span>
              </div>
              <div class="plant-emoji" aria-hidden="true">{emoji}</div>
              <h3>{escape(item['name'])}</h3>
              <p class="plant-role">{escape(str(row['role']))}</p>
              <div class="seed-stats">
                <span>⚔ {int(row['attack'])}</span>
                <span>🛡 {int(row['defense'])}</span>
                <span>🌀 {int(row['control'])}</span>
              </div>
              <div class="score-strip">单株指数 <strong>{item['unit_score']:.2f}</strong></div>
            </article>
            """
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
            f"""
            <article class="reason-card">
              <div class="reason-icon">{reason['emoji']}</div>
              <div>
                <div class="reason-title">
                  <strong>{escape(reason['name'])} × {reason['quantity']}</strong>
                  <span>{escape(str(reason['role']))}</span>
                </div>
                <p>{escape(reason['text'])}</p>
              </div>
            </article>
            """
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
        zombie_mode = st.selectbox(
            "僵尸模式",
            options=list(ZOMBIE_MODES),
            help="切换敌情会调整兼容战力权重并重新计算推荐。",
        )
        st.caption(ZOMBIE_MODES[zombie_mode]["description"])
        available_sun = st.slider("☀️ 可用阳光", 50, 500, 150, 25)
        available_cells = st.slider("🌱 草坪格子", 5, 45, 20, 5)
        st.markdown(
            """
            <div class="sidebar-note">
              <strong>离线可运行</strong>
              <span>当前使用仓库内 CSV 样例，不请求外部网站。</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("本页面只使用 emoji 与原创 CSS，不含官方游戏素材。")

    model = get_dashboard_model(zombie_mode, available_sun, available_cells)
    result = model["result"]

    render_hero(model, available_sun, available_cells)
    st.markdown(
        f'<div class="model-notice">🧪 <strong>{escape(model["score_label"])}</strong> · '
        f'{escape(model["score_notice"])}</div>',
        unsafe_allow_html=True,
    )
    render_constraint_bar(result)

    if not result["all_constraints_met"]:
        st.error(result["recommendation_reason"])
        return

    section_header(
        "SEED DECK",
        "植物推荐卡片",
        "每张种子卡展示成本、数量、定位与本轮兼容推荐指数。",
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
        "趋势来自本地离线样例；排行暂用兼容战力，正式指数将在第 4 批接入。",
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
        top_ranking = model["ranking"].head(10).set_index("name")[["utility"]]
        st.bar_chart(top_ranking, height=310, **stretch_width(st.bar_chart))
        st.caption("Top 10 兼容推荐指数；僵尸模式变化后自动重排。")

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
                "utility",
            ]
        ].rename(
            columns={
                "rank": "排名",
                "name": "植物",
                "vegetable_name": "映射蔬菜",
                "role": "定位",
                "sun_cost": "阳光成本",
                "latest_price": "最新菜价(元/kg)",
                "utility": "兼容推荐指数",
            }
        )
        st.dataframe(table, hide_index=True, **stretch_width(st.dataframe))
        st.json(
            {
                "求解状态": result["status"],
                "约束检查": result["constraint_checks"],
                "兼容权重": model["weights"],
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
