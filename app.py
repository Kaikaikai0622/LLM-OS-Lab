"""
🧪 LangGraph Sandbox Agent — Eval Dashboard

Streamlit 主页：项目介绍 + 导航入口。

启动方式：
    streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Agent Eval Dashboard",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 LangGraph Sandbox Agent")
st.subheader("智能上下文压缩让 AI 编程 Agent 的 Token 消耗降低 83%")

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
        ### 📊 Eval Dashboard
        三模式 × 多模型实验结果总览，包含 Token 增长曲线与跨模型对比。
        """
    )
    st.page_link("pages/1_eval_dashboard.py", label="打开 Eval Dashboard →", icon="📊")

with col2:
    st.markdown(
        """
        ### 🔬 A/B 模式对比
        选择两组实验日志，逐任务并排对比 Token、轮数、耗时与状态。
        """
    )
    st.page_link("pages/2_ab_compare.py", label="打开 A/B 对比 →", icon="🔬")

with col3:
    st.markdown(
        """
        ### 👤 场景决策指南
        基于 benchmark 数据的模式推荐决策树 + 虚拟用户 Persona。
        """
    )
    st.page_link("pages/3_scenario_guide.py", label="打开场景指南 →", icon="👤")

st.markdown("---")

st.markdown(
    """
    #### 📈 核心结果

    | 指标 | 效果 |
    |------|------|
    | Token 节省 | 最高 **83%** |
    | 交互轮次 | 14 轮 → 4 轮 |
    | 任务完成率 | **100%**（vs 50-75%）|
    | 等待时间 | ~40s → ~15s |

    #### 🏗️ 三种模式

    | 模式 | 特点 | 适用场景 |
    |------|------|----------|
    | **Native** | 零压缩，完整输出 | 简单 1-2 轮任务 |
    | **Baseline** | 截断输出（2000 chars） | 中等 3-5 轮任务 |
    | **Context Mode** | 压缩 + 索引 + 按需回查 | 复杂 5+ 轮迭代任务 |
    """
)

st.caption("数据来源：`logs/*.json` 实验日志 | 项目：LangGraph Sandbox Agent")
