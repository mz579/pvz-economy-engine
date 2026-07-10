"""PvZ Economy Engine Dashboard.

Multi-source interactive dashboard built with Streamlit.
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

from src.valuator import calculate_utility, calc_deviation
from src.optimizer import run_optimization

st.set_page_config(page_title="PvZ Economy Engine", page_icon="🌱", layout="wide")
st.title("🌱 PvZ Economy Engine")
st.caption("Multi-source data / Quantitative valuation / Operations optimization")

@st.cache_data
def load_plants():
    return pd.read_csv("data/plants.csv")

@st.cache_data
def load_prices():
    df = pd.read_csv("data/fallback/vegetable_prices.csv", encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data
def run_pipeline(swarm, tank, air, sun, cells):
    df_plants = load_plants()
    df_prices = load_prices()
    df_util = calculate_utility(df_plants)
    dev_df = calc_deviation(df_prices, df_util)
    df_merged = df_plants.merge(df_util[["name","utility","raw_utility"]], on="name")
    result = run_optimization(df_merged, dev_df, available_sun=sun, available_cells=cells, zombie_factor={"swarm":swarm,"tank":tank,"air":air})
    return {"df_plants": df_plants, "df_util": df_util, "dev_df": dev_df, "result": result}

with st.sidebar:
    st.header("⚙️ Controls")
    available_sun = st.slider("Initial Sun", 50, 500, 150, 10)
    available_cells = st.slider("Available Cells", 5, 50, 20, 1)
    st.subheader("🧟 Zombie Factors")
    swarm = st.slider("Swarm", 0.0, 1.0, 0.5, 0.05)
    tank = st.slider("Tank", 0.0, 1.0, 0.3, 0.05)
    air = st.slider("Air", 0.0, 1.0, 0.2, 0.05)
    run = st.button("🔄 Optimize", type="primary")

if "data" not in st.session_state:
    st.session_state.data = None
if run or st.session_state.data is None:
    with st.spinner("Optimizing..."):
        st.session_state.data = run_pipeline(swarm, tank, air, available_sun, available_cells)

data = st.session_state.data
result = data["result"]
dev_df = data["dev_df"]
df_plants = data["df_plants"]
df_util = data["df_util"]

st.subheader("🌿 Optimal Strategy")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Status", result["status"])
c2.metric("Total Utility", f"{result['total_utility']:.2f}")
c3.metric("Sun Cost", str(result["total_cost"]))
c4.metric("Plants", str(result["total_plants"]))

if result["strategy"]:
    items = list(result["strategy"].items())
    for i in range(0, len(items), 4):
        cols = st.columns(4)
        for j, (name, cnt) in enumerate(items[i:i+4]):
            pinfo = df_plants[df_plants["name"]==name].iloc[0]
            cols[j].markdown(f"""<div style="border:1px solid #4CAF50;border-radius:8px;padding:10px;text-align:center"><h4>{name}</h4><div style="font-size:28px;color:#4CAF50">x {cnt}</div><div style="font-size:12px;color:#666">☀️{pinfo['sun_cost']} | ⚔️{pinfo['attack']} | ❤️{pinfo['hp']}</div></div>""", unsafe_allow_html=True)
else:
    st.warning("No feasible solution for these parameters")

st.subheader("💰 Shadow Prices")
p1, p2, p3 = st.columns(3)
p1.metric("☀️ Sun", f"{result['sun_shadow_price']:.4f}", help="Marginal value of 1 extra sun")
p2.metric("🗺️ Cells", f"{result['cell_shadow_price']:.4f}", help="Marginal value of 1 extra cell")
sp = result.get("cost_shadow_price", 0)
p3.metric("💰 Budget", f"{sp:.4f}" if sp else "N/A")

if result["cell_shadow_price"] > result["sun_shadow_price"]:
    st.info("📊 Cells are more scarce than sun - consider expanding space")
elif result["sun_shadow_price"] > result["cell_shadow_price"]:
    st.info("📊 Sun is more scarce than cells - prioritize sun producers")

if dev_df is not None and not dev_df.empty:
    st.subheader("📈 Valuation Deviation")
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["#4CAF50" if s == "低估" else "#FF5722" for s in dev_df["signal"]]
    ax.barh(dev_df["plant"], dev_df["deviation"]*100, color=colors, edgecolor="white")
    ax.axvline(x=0, color="gray", ls="--", alpha=0.5)
    ax.set_xlabel("Deviation (%)")
    ax.legend(handles=[Patch(color="#4CAF50", label="Undervalued"), Patch(color="#FF5722", label="Overvalued")], loc="lower right")
    st.pyplot(fig)

if df_util is not None:
    st.subheader("📊 Utility Scores")
    show = df_util[["name","sun_cost","attack","hp","special_tag","utility"]].copy()
    show["utility"] = show["utility"].round(3)
    st.dataframe(show, use_container_width=True, hide_index=True)

with st.sidebar.expander("📋 Details"):
    if result["strategy"]:
        for p, c in sorted(result["strategy"].items(), key=lambda x: -x[1]):
            st.write(f"{p}: {c}")
    st.write(f"Utility: {result['total_utility']:.2f}")
    st.write(f"Sun: {result['total_cost']}")
st.sidebar.caption("PvZ Economy Engine v1.0")
