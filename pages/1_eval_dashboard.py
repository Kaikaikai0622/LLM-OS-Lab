"""
📊 Eval Dashboard — 三模式 × 多模型实验可视化

精简版：
  1. 模式总览对比（总 Token / 轮数 / 耗时 / 收敛率）
  2. Token 增长曲线（每轮累计 Token，三模式叠加）
  3. 跨模型对比（分组柱状图）
  4. 模型效率象限图（散点：x=总Token, y=完成率）
"""
import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 保证 lib 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.log_parser import load_all_logs

st.set_page_config(page_title="Eval Dashboard", page_icon="📊", layout="wide")
st.title("📊 Eval Dashboard")

# ---- 数据加载 ----
@st.cache_data
def get_data():
    return load_all_logs("logs")

df = get_data()

if df.empty:
    st.warning("未找到日志数据。请将实验 JSON 放入 `logs/` 目录。")
    st.stop()

# ---- Sidebar 筛选 ----
st.sidebar.header("筛选")
modes = st.sidebar.multiselect(
    "模式", df["mode_label"].unique().tolist(), default=df["mode_label"].unique().tolist()
)
models = st.sidebar.multiselect(
    "模型", df["model"].unique().tolist(), default=df["model"].unique().tolist()
)

filtered = df[df["mode_label"].isin(modes) & df["model"].isin(models)]

if filtered.empty:
    st.info("当前筛选无匹配数据，请调整筛选条件。")
    st.stop()

# ===========================================================================
# 1. 模式总览对比
# ===========================================================================
st.header("1. 模式总览对比")

# 按 mode_label + model 分组聚合
summary = (
    filtered.groupby(["mode_label", "model"])
    .agg(
        avg_tokens=("total_tokens", "mean"),
        avg_rounds=("round_count", "mean"),
        avg_time=("elapsed_seconds", "mean"),
        success_rate=("task_success", "mean"),
        task_count=("task_success", "count"),
    )
    .reset_index()
)
summary["success_rate_pct"] = (summary["success_rate"] * 100).round(1)

col1, col2 = st.columns(2)

with col1:
    fig_tokens = px.bar(
        summary, x="mode_label", y="avg_tokens", color="model",
        barmode="group", title="平均总 Token",
        labels={"mode_label": "模式", "avg_tokens": "Tokens", "model": "模型"},
    )
    st.plotly_chart(fig_tokens, width='stretch')

with col2:
    fig_rounds = px.bar(
        summary, x="mode_label", y="avg_rounds", color="model",
        barmode="group", title="平均交互轮次",
        labels={"mode_label": "模式", "avg_rounds": "轮次", "model": "模型"},
    )
    st.plotly_chart(fig_rounds, width='stretch')

col3, col4 = st.columns(2)

with col3:
    fig_time = px.bar(
        summary, x="mode_label", y="avg_time", color="model",
        barmode="group", title="平均耗时（秒）",
        labels={"mode_label": "模式", "avg_time": "秒", "model": "模型"},
    )
    st.plotly_chart(fig_time, width='stretch')

with col4:
    fig_success = px.bar(
        summary, x="mode_label", y="success_rate_pct", color="model",
        barmode="group", title="任务收敛率（%）",
        labels={"mode_label": "模式", "success_rate_pct": "%", "model": "模型"},
        range_y=[0, 105],
    )
    st.plotly_chart(fig_success, width='stretch')

# ===========================================================================
# 2. Token 增长曲线
# ===========================================================================
st.header("2. Token 增长曲线")

# 选择任务
task_options = filtered["task"].unique().tolist()
selected_task = st.selectbox("选择任务", task_options, index=0)

task_rows = filtered[filtered["task"] == selected_task]

fig_growth = go.Figure()
for _, row in task_rows.iterrows():
    rth = row["round_token_history"]
    if not rth:
        continue
    rounds = [r["round"] for r in rth]
    cum_tokens = []
    acc = 0
    for r in rth:
        acc += r["total_tokens"]
        cum_tokens.append(acc)
    label = f"{row['mode_label']} / {row['model']}"
    fig_growth.add_trace(go.Scatter(
        x=rounds, y=cum_tokens, mode="lines+markers", name=label,
    ))

fig_growth.update_layout(
    title=f"Token 累计增长 — {selected_task[:50]}",
    xaxis_title="轮次",
    yaxis_title="累计 Token",
    legend_title="模式 / 模型",
)
st.plotly_chart(fig_growth, width='stretch')

# ===========================================================================
# 3. 跨模型对比
# ===========================================================================
st.header("3. 跨模型对比")

model_summary = (
    filtered.groupby("model")
    .agg(
        avg_tokens=("total_tokens", "mean"),
        avg_rounds=("round_count", "mean"),
        success_rate=("task_success", "mean"),
        task_count=("task_success", "count"),
    )
    .reset_index()
)
model_summary["success_rate_pct"] = (model_summary["success_rate"] * 100).round(1)

col5, col6 = st.columns(2)
with col5:
    fig_model_tokens = px.bar(
        model_summary, x="model", y="avg_tokens",
        title="模型平均 Token 消耗",
        labels={"model": "模型", "avg_tokens": "Tokens"},
        color="model",
    )
    st.plotly_chart(fig_model_tokens, width='stretch')

with col6:
    fig_model_success = px.bar(
        model_summary, x="model", y="success_rate_pct",
        title="模型任务收敛率（%）",
        labels={"model": "模型", "success_rate_pct": "%"},
        color="model",
        range_y=[0, 105],
    )
    st.plotly_chart(fig_model_success, width='stretch')

# ===========================================================================
# 4. 模型效率象限图
# ===========================================================================
st.header("4. 模型效率象限图")

quadrant = (
    filtered.groupby(["mode_label", "model"])
    .agg(
        avg_tokens=("total_tokens", "mean"),
        success_rate=("task_success", "mean"),
        avg_rounds=("round_count", "mean"),
    )
    .reset_index()
)
quadrant["success_rate_pct"] = (quadrant["success_rate"] * 100).round(1)

fig_quad = px.scatter(
    quadrant,
    x="avg_tokens",
    y="success_rate_pct",
    color="model",
    symbol="mode_label",
    size="avg_rounds",
    hover_data=["mode_label", "model", "avg_rounds"],
    title="效率象限：Token 消耗 vs 任务完成率",
    labels={
        "avg_tokens": "平均总 Token",
        "success_rate_pct": "收敛率 (%)",
        "model": "模型",
        "mode_label": "模式",
    },
)
fig_quad.update_layout(yaxis_range=[0, 105])
# 理想区域标注（左上角 = 低 Token + 高成功率）
fig_quad.add_annotation(
    x=quadrant["avg_tokens"].min() * 0.9,
    y=102,
    text="← 理想区域（低 Token + 高完成率）",
    showarrow=False,
    font=dict(size=11, color="green"),
)
st.plotly_chart(fig_quad, width='stretch')

st.caption("数据来源：`logs/*.json` | 点大小 = 平均轮次")
