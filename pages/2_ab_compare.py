"""
🔬 A/B 模式对比 — 从 logs/*.json 回放历史结果，逐任务并排对比。

对齐策略：同 task_file + task_index JOIN。
"""
import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.log_parser import load_all_logs, get_available_logs

st.set_page_config(page_title="A/B 模式对比", page_icon="🔬", layout="wide")
st.title("🔬 A/B 模式对比")

# ---- 数据加载 ----
@st.cache_data
def get_data():
    return load_all_logs("logs")

df = get_data()

if df.empty:
    st.warning("未找到日志数据。请将实验 JSON 放入 `logs/` 目录。")
    st.stop()

# ---- 选择对比双方 ----
st.sidebar.header("选择对比日志")

log_labels = (df["mode_label"] + " / " + df["model"] + " (" + df["log_file"] + ")").unique().tolist()

# 构建 log_file -> label 映射
label_map = (
    df[["log_file", "mode_label", "model"]]
    .drop_duplicates("log_file")
    .assign(label=lambda d: d["mode_label"] + " / " + d["model"] + " (" + d["log_file"] + ")")
)
log_options = label_map["label"].tolist()

if len(log_options) < 2:
    st.warning("至少需要 2 个日志文件才能进行 A/B 对比。")
    st.stop()

sel_a = st.sidebar.selectbox("日志 A", log_options, index=0)
sel_b = st.sidebar.selectbox("日志 B", log_options, index=min(1, len(log_options) - 1))

file_a = label_map[label_map["label"] == sel_a]["log_file"].iloc[0]
file_b = label_map[label_map["label"] == sel_b]["log_file"].iloc[0]

df_a = df[df["log_file"] == file_a].copy()
df_b = df[df["log_file"] == file_b].copy()

# ---- 对齐检查 ----
task_file_a = df_a["config_task_file"].iloc[0] if not df_a.empty else ""
task_file_b = df_b["config_task_file"].iloc[0] if not df_b.empty else ""

if task_file_a != task_file_b:
    st.warning(
        f"⚠️ 两组日志使用不同 task_file（A: `{task_file_a}`, B: `{task_file_b}`），"
        "对比数据仅供参考。"
    )

# 按 task_index JOIN
merged = pd.merge(
    df_a, df_b,
    on="task_index",
    suffixes=("_a", "_b"),
    how="outer",
)

if merged.empty:
    st.info("两组日志无可对齐的任务。")
    st.stop()

# ---- 汇总指标卡片 ----
st.subheader("总览对比")

def safe_mean(series):
    return series.mean() if not series.empty else 0

mc1, mc2, mc3, mc4 = st.columns(4)

with mc1:
    st.metric(
        "平均 Token — A",
        f"{safe_mean(df_a['total_tokens']):,.0f}",
    )
    st.metric(
        "平均 Token — B",
        f"{safe_mean(df_b['total_tokens']):,.0f}",
        delta=f"{safe_mean(df_b['total_tokens']) - safe_mean(df_a['total_tokens']):+,.0f}",
        delta_color="inverse",
    )

with mc2:
    st.metric("平均轮次 — A", f"{safe_mean(df_a['round_count']):.1f}")
    st.metric(
        "平均轮次 — B",
        f"{safe_mean(df_b['round_count']):.1f}",
        delta=f"{safe_mean(df_b['round_count']) - safe_mean(df_a['round_count']):+.1f}",
        delta_color="inverse",
    )

with mc3:
    st.metric("平均耗时 — A", f"{safe_mean(df_a['elapsed_seconds']):.1f}s")
    st.metric(
        "平均耗时 — B",
        f"{safe_mean(df_b['elapsed_seconds']):.1f}s",
        delta=f"{safe_mean(df_b['elapsed_seconds']) - safe_mean(df_a['elapsed_seconds']):+.1f}s",
        delta_color="inverse",
    )

with mc4:
    rate_a = df_a["task_success"].mean() * 100 if not df_a.empty else 0
    rate_b = df_b["task_success"].mean() * 100 if not df_b.empty else 0
    st.metric("收敛率 — A", f"{rate_a:.0f}%")
    st.metric("收敛率 — B", f"{rate_b:.0f}%", delta=f"{rate_b - rate_a:+.0f}%")

st.markdown("---")

# ---- 逐任务对比 ----
st.subheader("逐任务对比")

for _, row in merged.iterrows():
    task_name = row.get("task_a") or row.get("task_b") or f"Task {row['task_index']}"
    with st.expander(f"Task {int(row['task_index'])}：{task_name[:60]}", expanded=False):
        ca, cb = st.columns(2)

        with ca:
            st.markdown(f"**A** — {sel_a}")
            if pd.notna(row.get("total_tokens_a")):
                st.write(f"- 轮次: **{int(row['round_count_a'])}**")
                st.write(f"- Token: **{int(row['total_tokens_a']):,}**")
                st.write(f"- 耗时: **{row['elapsed_seconds_a']:.1f}s**")
                st.write(f"- 状态: {row['status_emoji_a']}")
            else:
                st.write("N/A")

        with cb:
            st.markdown(f"**B** — {sel_b}")
            if pd.notna(row.get("total_tokens_b")):
                st.write(f"- 轮次: **{int(row['round_count_b'])}**")
                st.write(f"- Token: **{int(row['total_tokens_b']):,}**")
                st.write(f"- 耗时: **{row['elapsed_seconds_b']:.1f}s**")
                st.write(f"- 状态: {row['status_emoji_b']}")
            else:
                st.write("N/A")

        # Token 增长曲线叠加
        rth_a = row.get("round_token_history_a", []) or []
        rth_b = row.get("round_token_history_b", []) or []

        if rth_a or rth_b:
            fig = go.Figure()
            for rth, name in [(rth_a, "A"), (rth_b, "B")]:
                if not rth:
                    continue
                rounds = [r["round"] for r in rth]
                cum = []
                acc = 0
                for r in rth:
                    acc += r["total_tokens"]
                    cum.append(acc)
                fig.add_trace(go.Scatter(
                    x=rounds, y=cum, mode="lines+markers", name=name,
                ))
            fig.update_layout(
                height=300,
                margin=dict(t=30, b=30),
                xaxis_title="轮次",
                yaxis_title="累计 Token",
            )
            st.plotly_chart(fig, width='stretch')

st.caption("对齐策略：按 task_index JOIN，要求同 task_file 同 batch 的日志。")
