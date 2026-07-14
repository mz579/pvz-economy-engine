"""PvZ-inspired Streamlit dashboard for the V2.0 recommendation system."""

from __future__ import annotations

from html import escape
import inspect
from math import isfinite
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


def format_number(value: object, *, decimals: int = 2, missing: str = "—") -> str:
    """Format numeric view data without turning missing values into zeroes."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return missing
    if not isfinite(number):
        return missing
    return f"{number:.{decimals}f}"


def format_price(value: object, unit: object) -> str:
    """Format one real price with its model-provided normalized unit."""

    number = format_number(value, missing="")
    if not number or not unit:
        return "未映射菜价"
    return f"{number} {unit}"


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
    elif (
        st.session_state.get(ANALYSIS_MODEL_KEY) is not None
        and not st.session_state[ANALYSIS_MODEL_KEY]["result"]["all_constraints_met"]
    ):
        css_class = "is-error"
        icon = "!"
        title = "方案不可行"
        copy = "分析已完成，但当前条件无法满足组合约束。"
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


def render_hero(model: dict) -> None:
    """Render the compact command terminal header for the submitted analysis."""

    mode = model["mode"]
    result = model["result"]
    if st.session_state.get(ANALYSIS_ERROR_KEY):
        status_class = "is-warning"
        status_icon = "⚠"
        status_text = "输入待修正"
    elif result["all_constraints_met"]:
        status_class = "is-success"
        status_icon = "✓"
        status_text = "分析完成"
    else:
        status_class = "is-error"
        status_icon = "!"
        status_text = "方案不可行"
    st.markdown(
        f"""
        <section class="terminal-header" aria-label="末日菜园作战终端">
          <div class="terminal-brand">
            <div class="terminal-kicker">GARDEN DEFENSE CONSOLE · V2.0</div>
            <h1>末日菜园作战室</h1>
          </div>
          <div class="terminal-readout" aria-label="当前分析场景">
            <span><small>当前模式</small><strong>{escape(mode['icon'])} {escape(model['zombie_mode'])}</strong></span>
            <span><small>情报来源</small><strong>{escape(model['data_source'])}</strong></span>
            <span><small>数据日期</small><strong>{model['latest_date'].strftime('%Y-%m-%d')}</strong></span>
            <span class="terminal-status {status_class}" role="status">
              <small>分析状态</small><strong>{status_icon} {status_text}</strong>
            </span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def build_lawn_slots(model: dict, available_cells: int) -> list[dict[str, object]]:
    """Expand the recommendation into an exact-capacity display-only lawn."""

    slots: list[dict[str, object]] = []
    for item in model["result"]["combination"]:
        quantity = int(item["quantity"])
        for _ in range(quantity):
            slots.append(
                {
                    "name": str(item["name"]),
                    "emoji": PLANT_EMOJI.get(item["name"], "🌱"),
                    "occupied": True,
                }
            )
    slots = slots[:available_cells]
    slots.extend(
        {"name": "空格", "emoji": "", "occupied": False}
        for _ in range(available_cells - len(slots))
    )
    return slots


def render_recommendation_summary(
    model: dict,
    available_sun: int,
    available_cells: int,
) -> None:
    """Put the complete order, resources and display lawn above the fold."""

    result = model["result"]
    feasible = bool(result["all_constraints_met"])
    state_class = "is-success" if feasible else "is-infeasible"
    state_icon = "✓" if feasible else "!"
    state_title = "分析完成" if feasible else "方案不可行"
    heading = "本轮建议种植" if feasible else "本轮暂无可行种植方案"

    if feasible:
        ranking = model["ranking"].set_index("name")
        planting_cards = []
        for item in result["combination"]:
            row = ranking.loc[item["name"]]
            unit = model["price_unit"]
            planting_cards.append(
                f'<article class="roster-card" '
                f'aria-label="{escape(item["name"])} {item["quantity"]} 株">'
                f'<div class="roster-identity">'
                f'<span class="roster-emoji" aria-hidden="true">'
                f'{PLANT_EMOJI.get(item["name"], "🌱")}</span>'
                f'<div><strong>{escape(item["name"])}</strong>'
                f'<span>{escape(str(row["vegetable_name"]))} · {escape(str(row["role"]))}</span></div>'
                f'<b>× {item["quantity"]}</b></div>'
                f'<div class="roster-market">'
                f'<span><small>当前单价</small><strong>{escape(format_price(row["current_price"], unit))}</strong></span>'
                f'<span><small>样本均价</small><strong>{escape(format_price(row["historical_mean"], unit))}</strong></span>'
                f'</div>'
                f'<div class="roster-metrics">'
                f'<span>☀ {item["unit_sun_cost"]} / 株</span>'
                f'<span>相对评分 {row["apocalypse_index"]:.4f}</span>'
                f'<span>排名 #{int(row["rank"])}</span>'
                f'</div></article>'
            )
        planting_html = "".join(planting_cards)
        summary_copy = "结果对应最近一次提交；左侧参数修改后，再次点击“开始分析”才会更新。"
    else:
        planting_html = (
            '<div class="infeasible-copy" role="alert">'
            '<strong>当前配置无法组成合法阵容</strong>'
            f'<p>{escape(result["recommendation_reason"])} 请调整阳光、格子或菜价覆盖后重新分析。</p>'
            '</div>'
        )
        summary_copy = "系统没有隐藏结果：当前条件确实无法同时满足攻击与防御/控制要求。"

    score_value = f'{result["total_score"]:.2f}' if feasible else "—"
    resource_html = "".join(
        f'<div class="resource-counter">'
        f'<span aria-hidden="true">{icon}</span>'
        f'<div><small>{escape(label)}</small><strong>{escape(value)}</strong></div>'
        f'</div>'
        for icon, label, value in (
            ("☀", "阳光消耗", f"{result['total_sun_cost']} / {available_sun}"),
            ("▦", "草坪占用", f"{result['total_plants']} / {available_cells}"),
            ("◆", "组合相对比较指数", score_value),
            (
                "◎",
                "菜价映射",
                f"{model['coverage']['matched_plants']} / {model['coverage']['total_plants']}",
            ),
        )
    )

    lawn_cells = []
    for index, slot in enumerate(build_lawn_slots(model, available_cells), start=1):
        if bool(slot["occupied"]):
            name = escape(str(slot["name"]))
            lawn_cells.append(
                f'<div class="lawn-cell is-occupied" data-slot="{index}" '
                f'data-plant="{name}" title="第 {index} 格：{name}" '
                f'aria-label="第 {index} 格，{name}">'
                f'<span aria-hidden="true">{slot["emoji"]}</span><small>{name}</small></div>'
            )
        else:
            lawn_cells.append(
                f'<div class="lawn-cell is-empty" data-slot="{index}" '
                f'title="第 {index} 格：空位" aria-label="第 {index} 格，空位">'
                f'<span aria-hidden="true">·</span><small>空位</small></div>'
            )
    lawn_html = "".join(lawn_cells)
    occupied_count = int(result["total_plants"]) if feasible else 0

    st.markdown(
        f"""
        <section class="recommendation-summary {state_class}" aria-label="本轮阵容与草坪部署">
          <div class="recommendation-heading">
            <div>
              <span class="result-kicker">CURRENT SQUAD</span>
              <h2>{heading}</h2>
            </div>
            <span class="result-state {state_class}" role="status">{state_icon} {state_title}</span>
          </div>
          <div class="resource-strip">{resource_html}</div>
          <div class="deployment-stage">
            <section class="roster-sheet" aria-label="推荐植物清单">
              <header><span>本轮阵容</span><strong>{len(result['combination'])} 种 / {result['total_plants']} 株</strong></header>
              <div class="roster-list">{planting_html}</div>
              <p class="summary-copy">{summary_copy}</p>
            </section>
            <section class="lawn-panel" aria-label="阵容展示布局">
              <header>
                <div><span>LAWN DEPLOYMENT</span><strong>阵容展示布局</strong></div>
                <b>{occupied_count} / {available_cells} 格</b>
              </header>
              <div class="lawn-direction" aria-hidden="true"><span>后方</span><i></i><span>前线</span></div>
              <div class="lawn-board">{lawn_html}</div>
              <p>格子仅用于数量核对，非优化器计算出的最优坐标。</p>
            </section>
          </div>
          <div class="index-explainer"><strong>◆ 相对比较指数</strong><span>
          仅用于当前候选植物之间比较；越高表示当前模型下越值得选择。它不是百分制、收益率或成功概率。</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_coverage_notice(model: dict) -> None:
    """Make partial user-data coverage explicit without treating it as failure."""

    coverage = model["coverage"]
    if not coverage["excluded_plants"]:
        return
    excluded = "、".join(coverage["excluded_plants"])
    st.markdown(
        f"""
        <aside class="coverage-notice" role="status" aria-label="部分菜价映射提示">
          <span aria-hidden="true">⚠️</span>
          <div>
            <strong>部分菜价已成功映射</strong>
            <p>本次关联 {coverage['matched_plants']} / {coverage['total_plants']} 种植物；
            缺少对应菜价的植物未参与本轮比较：{escape(excluded)}。</p>
          </div>
        </aside>
        """,
        unsafe_allow_html=True,
    )


def render_candidate_comparison(model: dict) -> None:
    """Compare every mapped and unmapped plant without inventing market data."""

    coverage = model["coverage"]
    unmatched_count = coverage["total_plants"] - coverage["matched_plants"]
    section_header(
        "MARKET INTELLIGENCE",
        "市场情报",
        "先核对本轮数据口径，再比较全部候选植物。未映射项目保留作战属性，但不伪造价格或评分。",
    )
    st.markdown(
        f"""
        <div class="data-scope" aria-label="菜价数据口径">
          <span><small>价格单位</small><strong>{escape(model['price_unit'])}</strong>
          <em>清洗后标准单位</em></span>
          <span><small>数据日期</small><strong>{model['latest_date'].strftime('%Y-%m-%d')}</strong></span>
          <span><small>数据来源</small><strong>{escape(model['data_source'])}</strong></span>
          <span><small>使用模式</small><strong>{escape(model['data_mode'])}</strong></span>
          <span><small>映射覆盖</small><strong>{coverage['matched_plants']} 已映射 / {unmatched_count} 未映射</strong></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ranking = model["ranking"]
    top_row = ranking.iloc[0]
    selected_ranks = sorted(
        int(row["rank"])
        for _, row in ranking.loc[
            ranking["name"].isin(model["result"]["strategy"])
        ].iterrows()
    )
    selected_rank_text = (
        "、".join(f"#{rank_value}" for rank_value in selected_ranks)
        if selected_ranks
        else "暂无"
    )
    st.markdown(
        f"""
        <div class="intel-strip" aria-label="市场情报摘要">
          <span><small>当前评分首位</small><strong>{escape(str(top_row['name']))}</strong>
          <em>{top_row['apocalypse_index']:.4f}</em></span>
          <span><small>本轮入选排名</small><strong>{escape(selected_rank_text)}</strong>
          <em>按单株相对评分</em></span>
          <span><small>样本菜品</small><strong>{model['prices']['name'].nunique()} 种</strong>
          <em>{len(model['prices'])} 条价格记录</em></span>
        </div>
        <div class="table-heading">
          <div><span>CANDIDATE BOARD</span><strong>全部候选植物对比</strong></div>
          <p>默认按单株相对评分从高到低排列</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    price_rows = []
    combat_rows = []
    for _, row in model["candidate_comparison"].iterrows():
        selected = (
            f"✅ 已入选 × {int(row['selected_quantity'])}"
            if bool(row["selected"])
            else "—"
        )
        has_price = bool(row["has_price"])
        unit = row["price_unit"] if has_price else None
        if has_price:
            difference_value = float(row["price_difference"])
            difference = f"{difference_value:+.2f} {unit}"
            current_price = format_price(row["current_price"], unit)
            average_price = format_price(row["historical_mean"], unit)
            score = format_number(row["apocalypse_index"], decimals=4)
            rank = f"#{int(row['rank'])}"
        else:
            difference = "未映射菜价"
            current_price = "未映射菜价"
            average_price = "未映射菜价"
            score = "—"
            rank = "—"

        price_rows.append(
            {
                "是否入选": selected,
                "评分排名": rank,
                "植物名称": row["name"],
                "对应蔬菜": row["vegetable_name"],
                "当前单价": current_price,
                "平均价": average_price,
                "较均价差异": difference,
                "阳光成本": f"{row['sun_cost']} / 株",
                "相对评分": score,
            }
        )
        combat_rows.append(
            {
                "是否入选": selected,
                "植物名称": row["name"],
                "定位": row["role"],
                "攻击": row["attack"],
                "防御": row["defense"],
                "生产": row["production"],
                "控制": row["control"],
                "特殊能力": row["special_ability"],
            }
        )

    price_tab, combat_tab = st.tabs(["💰 价格与评分", "🛡️ 作战属性"])
    with price_tab:
        st.caption("价格均显示清洗后的实际数值与单位；“—”表示该字段无法参与本轮相对比较。")
        st.dataframe(
            price_rows,
            hide_index=True,
            height=500,
            **stretch_width(st.dataframe),
        )
    with combat_tab:
        st.caption("未映射菜价的植物仍保留原始作战属性，便于检查映射缺口。")
        st.dataframe(
            combat_rows,
            hide_index=True,
            height=500,
            **stretch_width(st.dataframe),
        )


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


def render_market_section(model: dict) -> None:
    """Render price evidence after the recommendation and its reasons."""

    section_header(
        "MARKET INTEL",
        "市场数据和趋势",
        "查看菜价变化与单株相对比较指数；这些数据用于解释推荐，而不是收益率预测。",
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
        st.caption(
            f"{selected_vegetable} · 单位：{model['price_unit']} · 来源：{model['data_source']}"
        )
    with chart_right:
        top_ranking = (
            model["ranking"]
            .head(10)
            .set_index("name")[["apocalypse_index"]]
            .rename(columns={"apocalypse_index": "单株相对比较指数"})
        )
        st.bar_chart(top_ranking, height=310, **stretch_width(st.bar_chart))
        st.caption("Top 10 单株相对比较指数；只用于同一模型内横向比较。")


def render_technical_details(model: dict) -> None:
    """Keep solver, formula, constraints and raw model state below the results."""

    result = model["result"]
    with st.expander("模型说明与技术细节"):
        solver_label = "整数规划" if result["method"] == "pulp" else "贪心兜底"
        st.markdown(
            f'<div class="model-notice">🧪 <strong>{escape(model["score_label"])}</strong> · '
            f'{escape(model["score_notice"])}。总评分在页面中标为“相对比较指数”，'
            f'不是百分制、收益率或成功概率。</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="technical-facts">'
            f'<span><strong>求解方式</strong>{escape(solver_label)}</span>'
            f'<span><strong>求解状态</strong>{escape(str(result["status"]))}</span>'
            f'<span><strong>菜价来源</strong>{escape(model["data_source"])}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        render_constraint_bar(result)
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
                "latest_price": f"最新菜价({model['price_unit']})",
                "battle_value": "战斗价值",
                "price_undervaluation": "价格低估系数",
                "stability_coefficient": "稳定性系数",
                "apocalypse_index": "单株相对比较指数",
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

    render_hero(model)
    render_recommendation_summary(model, available_sun, available_cells)
    render_coverage_notice(model)

    if result["all_constraints_met"]:
        displayed_reason = result["recommendation_reason"].replace(
            "总评分", "相对比较指数"
        )
        section_header(
            "WHY THIS TEAM",
            "推荐原因",
            displayed_reason,
        )
        render_reasons(model)

    render_candidate_comparison(model)

    if result["all_constraints_met"]:
        render_market_section(model)

    render_technical_details(model)

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
