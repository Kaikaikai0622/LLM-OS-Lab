"""
👤 场景决策指南 — 模式推荐决策树 + 虚拟用户 Persona。
"""
import streamlit as st

st.set_page_config(page_title="场景决策指南", page_icon="👤", layout="wide")
st.title("👤 场景决策指南")

# ===========================================================================
# 决策树
# ===========================================================================
st.header("🌲 模式选择决策树")

st.markdown(
    """
    ```
    任务预估轮数?
    ├── 1-2 轮（简单计算 / 查询）
    │   └── ✅ Native Mode — 零开销，最低延迟
    ├── 3-5 轮（中等复杂度）
    │   └── ✅ Baseline Mode — 截断防膨胀，无额外工具负担
    └── 5+ 轮（迭代调试 / 复杂算法）
        └── ✅ Context Mode — 压缩 + 索引，Token 节省 50-83%
    ```
    """
)

st.markdown("---")

st.markdown(
    """
    | 任务类型 | 推荐模式 | 原因 |
    |----------|----------|------|
    | 一次性输出（生成代码/文档） | **Native** | 无需多轮，压缩反而增加延迟 |
    | 调试修复（错误→修复→验证循环） | **Context Mode** | 多轮迭代，历史压缩收益最大 |
    | 探索性分析（多步数据处理） | **Context Mode** | 中间输出可索引回查 |
    | 代码审查（读取+评价） | **Baseline** | 输出适中，截断即够 |
    | 简单计算 | **Native** | 1 轮即完成 |
    """
)

# ===========================================================================
# 虚拟用户 Persona
# ===========================================================================
st.header("🧑‍💻 虚拟用户 Persona")

personas = [
    {
        "icon": "🧑‍💻",
        "name": "小明",
        "role": "前端实习生",
        "task": "帮我写一个排序算法",
        "pain": "简单任务不需要复杂框架，追求低延迟",
        "mode": "Native",
        "reason": "1 轮即出结果，零额外开销",
    },
    {
        "icon": "👩‍🔬",
        "name": "李博士",
        "role": "数据科学家",
        "task": "用高斯消元解线性方程组，打印中间步骤",
        "pain": "输出很长、多轮迭代、Token 爆炸",
        "mode": "Context Mode",
        "reason": "压缩长输出 + 保留索引，14 轮→4 轮",
    },
    {
        "icon": "🧑‍🏫",
        "name": "王老师",
        "role": "CS 教师",
        "task": "比较 5 种排序算法的性能",
        "pain": "复杂任务经常超时或达到执行上限",
        "mode": "Context Mode",
        "reason": "收敛率从 50% 提升到 100%",
    },
    {
        "icon": "👨‍💼",
        "name": "张经理",
        "role": "技术管理者",
        "task": "控制 API 每月调用成本",
        "pain": "关注成本而非速度",
        "mode": "Context Mode",
        "reason": "Token 消耗降低 83%，直接节省 API 费用",
    },
    {
        "icon": "🧑‍🎨",
        "name": "陈设计",
        "role": "全栈开发者",
        "task": "快速验证一个 idea",
        "pain": "需要低延迟反馈",
        "mode": "Native / Baseline",
        "reason": "简单验证用 Native，稍复杂用 Baseline",
    },
]

cols = st.columns(len(personas))
for col, p in zip(cols, personas):
    with col:
        st.markdown(f"### {p['icon']} {p['name']}")
        st.caption(p["role"])
        st.markdown(f"**典型任务**：{p['task']}")
        st.markdown(f"**痛点**：{p['pain']}")
        st.success(f"推荐：**{p['mode']}**")
        st.caption(p["reason"])

st.caption("Persona 基于 benchmark 数据和典型开发者画像构建。")
