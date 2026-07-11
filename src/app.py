"""PvZ Economy Engine Dashboard - Multi-source with region selector.

V1.0: Interactive region switching with full pipeline linkage.
"""
import sys; sys.path.insert(0, ".")
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from typing import Optional

from src.valuator import calculate_utility, calc_deviation, adjust_weights_by_zombie_factor
from src.optimizer import run_optimization

st.set_page_config(page_title="PvZ Economy Engine", page_icon="\U0001F331", layout="wide")
st.title("\U0001F331 PvZ Economy Engine")
st.caption("Multi-source data / Quantitative valuation / Operations optimization / Style rotation")

# ---------------------------------------------------------------------------
# Region data mapping
# ---------------------------------------------------------------------------
REGION_FILES: dict = {
    "xinfadi":    {"path": "data/fallback/vegetable_prices.csv",    "label": "\u5317\u4eac\u65b0\u53d1\u5730\u6279\u53d1\u5e02\u573a"},
    "shouguang":  {"path": "data/shouguang/shouguang_prices.csv",  "label": "\u5c71\u4e1c\u5bff\u5149\u852c\u83dc\u4ef7\u683c\u6307\u6570"},
}

REGION_KEYS = list(REGION_FILES.keys())


@st.cache_data(ttl=3600)
def load_plants():
    return pd.read_csv("data/plants.csv")


@st.cache_data(ttl=3600)
def load_prices(region_key: str) -> Optional[pd.DataFrame]:
    """Load price data for a given region, with optional custom upload."""
    info = REGION_FILES.get(region_key)
    if info is None:
        return None
    try:
        df = pd.read_csv(info["path"], encoding="utf-8-sig")
        df["date"] = pd.to_datetime(df["date"])
        df["source"] = region_key
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600)
def run_pipeline(region_key: str, swarm: float, tank: float, air: float, sun: int, cells: int):
    """Full pipeline: load -> valuate -> optimize."""
    df_plants = load_plants()
    df_prices = load_prices(region_key)
    if df_prices is None or df_prices.empty:
        return {"error": f"No price data for region: {region_key}"}

    # Adjust weights by zombie factor
    adjusted_weights = adjust_weights_by_zombie_factor({"swarm": swarm, "tank": tank, "air": air})

    # Calculate utility with adjusted weights
    df_util = calculate_utility(df_plants, weights=adjusted_weights)
    dev_df = calc_deviation(df_prices, df_util)

    # Merge and optimize
    df_merged = df_plants.merge(df_util[["name", "utility", "raw_utility"]], on="name")
    result = run_optimization(
        df_merged, dev_df,
        available_sun=sun, available_cells=cells,
        zombie_factor={"swarm": swarm, "tank": tank, "air": air},
    )

    return {
        "region": region_key,
        "plants": df_plants,
        "util": df_util,
        "deviation": dev_df,
        "result": result,
        "weights": adjusted_weights,
        "prices": df_prices,
    }


def show_strategy_card(result: dict):
    """Display optimal strategy as cards."""
    st.subheader("\U0001F336 Optimal Strategy")
    if not result["strategy"]:
        st.warning("No feasible solution for these parameters")
        return

    items = list(result["strategy"].items())
    for i in range(0, len(items), 4):
        cols = st.columns(4)
        for j, (name, cnt) in enumerate(items[i:i + 4]):
            pinfo = load_plants()[load_plants()["name"] == name].iloc[0]
            cols[j].markdown(
                f"""<div style="border:1px solid #4CAF50;border-radius:8px;padding:10px;text-align:center">
                <h4>{name}</h4>
                <div style="font-size:28px;color:#4CAF50">x {cnt}</div>
                <div style="font-size:12px;color:#666">\u2606\uFE0F{pinfo['sun_cost']} | \u2694\uFE0F{pinfo['attack']} | \u2764\uFE0F{pinfo['hp']}</div>
                </div>""",
                unsafe_allow_html=True,
            )


def show_shadow_prices(result: dict):
    """Display shadow price analysis."""
    st.subheader("\U0001F4B5 Shadow Prices")
    p1, p2, p3 = st.columns(3)
    sun_sp = result.get("sun_shadow_price", 0)
    cell_sp = result.get("cell_shadow_price", 0)
    p1.metric("\u2606\uFE0F Sun", f"{sun_sp:.4f}", help="Marginal value of 1 extra sun")
    p2.metric("\U0001F337 Cells", f"{cell_sp:.4f}", help="Marginal value of 1 extra cell")

    if cell_sp > sun_sp:
        st.info("\U0001F4F3 Cells are more scarce than sun - consider expanding space")
    elif sun_sp > cell_sp:
        st.info("\U0001F4F3 Sun is more scarce than cells - prioritize sun producers")
    else:
        st.info("\U0001F4F3 Both resources are balanced in marginal value")


def show_deviation_chart(dev_df: pd.DataFrame):
    """Display valuation deviation bar chart."""
    if dev_df is None or dev_df.empty:
        return
    st.subheader("\U0001F4B1 Valuation Deviation")
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["#4CAF50" if s == "\u4f4e\u4f30" else "#FF5722" for s in dev_df["signal"]]
    ax.barh(dev_df["plant"], dev_df["deviation"] * 100, color=colors, edgecolor="white")
    ax.axvline(x=0, color="gray", ls="--", alpha=0.5)
    ax.set_xlabel("Deviation (%)")
    ax.legend(
        handles=[Patch(color="#4CAF50", label="Undervalued"), Patch(color="#FF5722", label="Overvalued")],
        loc="lower right",
    )
    st.pyplot(fig)


def show_weights_info(weights: dict):
    """Show adjusted utility weights."""
    st.subheader("\U0001F3AF Active Weights")
    for k, v in weights.items():
        label_map = {"attack": "\u2694\uFE0F Attack", "hp": "\u2764\uFE0F HP", "special": "\u2728 Special"}
        st.metric(label_map.get(k, k), f"{v:.3f}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("\U00002699\uFE0F Controls")

    # Region selector
    region_labels = {k: v["label"] for k, v in REGION_FILES.items()}
    region_keys = list(region_labels.keys())
    region_display = [region_labels[k] for k in region_keys]
    selected_idx = region_keys.index("xinfadi") if "xinfadi" in region_keys else 0
    selected_region = st.selectbox(
        "\U0001F30D Region",
        options=region_keys,
        format_func=lambda x: region_labels.get(x, x),
        index=selected_idx,
    )

    # Resource sliders
    available_sun = st.slider("Initial Sun", 50, 500, 150, 10)
    available_cells = st.slider("Available Cells", 5, 50, 20, 1)

    # Zombie factor sliders (style rotation)
    st.subheader("\U0001F9DC Zombie Factors")
    swarm = st.slider("Swarm", 0.0, 1.0, 0.5, 0.05, help="Swarm zombies -> boost AOE/Splash value")
    tank = st.slider("Tank", 0.0, 1.0, 0.3, 0.05, help="Tank zombies -> boost high-damage value")
    air = st.slider("Air", 0.0, 1.0, 0.2, 0.05, help="Air zombies -> boost special/utility value")

    run = st.button("\U0001F9E9 Optimize", type="primary")

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
if "data" not in st.session_state:
    st.session_state.data = None

if run or st.session_state.data is None:
    with st.spinner("Running pipeline..."):
        st.session_state.data = run_pipeline(
            selected_region, swarm, tank, air, available_sun, available_cells
        )

data = st.session_state.data

# Handle errors
if isinstance(data, dict) and "error" in data:
    st.error(data["error"])
    st.stop()

result = data["result"]
dev_df = data["deviation"]
util_df = data["util"]
prices = data["prices"]

# Source indicator
col_region, col_status, col_util, col_cost, col_count = st.columns(5)
region_display_name = REGION_FILES.get(data["region"], {}).get("label", data["region"])
col_region.metric("\U0001F30D Source", region_display_name)
col_status.metric("Status", result["status"])
col_util.metric("Total Utility", f"{result['total_utility']:.2f}")
col_cost.metric("Sun Cost", str(result["total_cost"]))
col_count.metric("Plants", str(result["total_plants"]))

# Optimal strategy cards
show_strategy_card(result)

# Shadow prices
show_shadow_prices(result)

# Layout: deviation + weights side by side
col_left, col_right = st.columns([3, 1])
with col_left:
    show_deviation_chart(dev_df)
with col_right:
    show_weights_info(data["weights"])

# Utility table
if util_df is not None:
    st.subheader("\U0001F4CA Utility Scores")
    show = util_df[["name", "sun_cost", "attack", "hp", "special_tag", "utility"]].copy()
    show["utility"] = show["utility"].round(3)
    st.dataframe(show, use_container_width=True, hide_index=True)

# Forecast summary from latest prices
if prices is not None and not prices.empty:
    st.subheader("\U0001F4C8 Latest Price Snapshot")
    latest = prices[prices["date"] == prices["date"].max()]
    if not latest.empty:
        avg_price = latest.groupby("product")["price"].mean().reset_index()
        avg_price = avg_price.sort_values("price", ascending=False)
        avg_price["price"] = avg_price["price"].round(2)
        avg_price.columns = ["Product", "Price (\u5143/kg)"]
        st.dataframe(avg_price, use_container_width=True, hide_index=True)

# Sidebar expanders
with st.sidebar.expander("\U0001F4CB Strategy Details"):
    if result["strategy"]:
        for p, c in sorted(result["strategy"].items(), key=lambda x: -x[1]):
            st.write(f"{p}: {c}")
    st.write(f"Utility: {result['total_utility']:.2f}")
    st.write(f"Sun: {result['total_cost']}")

st.sidebar.caption("PvZ Economy Engine v1.0 \u2022 Multi-source \u2022 MIP Optimizer")
