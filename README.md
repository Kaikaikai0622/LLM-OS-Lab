# 🧪 LangGraph Sandbox Agent

>在经历了上一次的多Agent Orchestration失败后，我回过头探索单Agent的能力边界，着眼目前编程Agent的核心痛点--上下文工程。我相信目前最强的单体Agent还远远没有触及（Openclaw还不足够），上下文工程是这个发展过程中的核心难点之一，本项目作为该痛点的众多解决思路之一的试验，同时作为我对“Agent是围绕LLM构建的操作系统”（Agent Harness）这一技术理念的践行和学习。


> **上下文工程驱动的 AI 编程 Agent** — 不换模型，Token 消耗降低 83%，任务完成率从 70% 提升至 100%。

一个基于 LangGraph 构建的代码执行 Agent，配备完整的 **Eval 体系**、**Agent SDK** 与 **多模型横评框架**。项目证明：通过上下文工程（Context Engineering）而非更强的基座模型，即可系统性解决多轮工具调用中的 Token 膨胀问题。

---

## ⚡ 快速了解

```
痛点：AI 编程 Agent 在多轮迭代中，历史输出累积 → Token 线性膨胀 → 超时/失败/成本飙升

方案：三层上下文压缩管线
  1. 执行输出 → 索引存储（UUID 映射完整结果）→ 压缩摘要返回 LLM
  2. 旧消息 → 压缩为引用（保留 execution_id）→ 仅保留最近 3 轮完整
  3. 按需回查 → LLM 调用 fetch_execution_detail 检索特定历史

结果：Token ↓83% | 轮次 14→4 | 完成率 50%→100% | Prompt 峰值 ↓60%
```

---

## 📊 Eval 结果

在 4 个编程任务（斐波那契、高斯消元、数值积分、排序算法比较）上横评三种上下文策略：

| 指标 | Native | Baseline | **Context Mode** |
|------|--------|----------|-----------------|
| **排序任务 Token** | 130,320 | 453,936 | **22,766** (↓83%) |
| **排序任务轮数** | 14 (达上限) | 25 (达上限) | **4** (收敛) |
| **高斯消元 Token** | 12,803 | 12,150 | **6,147** (↓52%) |
| **任务完成率** | 75% | 50% | **100%** |
| **Prompt 峰值** | 15,203 | 33,173 | **6,018** |

> Context Mode 在第 2-3 轮即可收回压缩开销，之后 Token 曲线趋于平稳，而 Native/Baseline 持续线性增长。

### Eval 方法论

- **指标体系**：Token 消耗、交互轮次、LLM 延迟、工具延迟、压缩比、任务收敛率、stop_reason 分布
- **数据采集**：Agent 运行时自动埋点，结构化写入 JSON log（含 `round_token_history`、`per_round_llm_latency` 等）
- **可视化**：Jupyter Notebook 8 类图表（柱状图、折线图、热力图、漏斗图、散点图…）
- **跨模型横评**：CLI `--model` 参数支持同一 benchmark 对比不同 LLM（qwen-plus / qwen-turbo / gpt-4o-mini），Dashboard 自动生成 Section 9 分组对比 + Section 10 效率象限图

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         SandboxAgent                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   agent_node │ →  │ tool_executor│ →  │ compress_old_messages│ │
│  │   (LLM)      │    │ (Pyodide)    │    │ (压缩旧消息)         │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│         ↑                                    │                  │
│         └────────────────────────────────────┘                  │
│                    (StateGraph 循环)                            │
├─────────────────────────────────────────────────────────────────┤
│  InMemoryIndexStore: execution_id → 完整输出                    │
│  fetch_execution_detail: 按需检索历史详情                       │
├─────────────────────────────────────────────────────────────────┤
│  AgentBuilder SDK: .llm() .sandbox() .system_prompt() .build()  │
│  Eval Pipeline: 埋点 → JSON log → Notebook/Streamlit 可视化    │
└─────────────────────────────────────────────────────────────────┘
```

### 三种上下文策略

| 策略 | 索引 | 消息压缩 | Fetch 工具 | 适用场景 |
|------|------|----------|------------|----------|
| **Native** | 无 | 无 | 无 | 1-2 轮简单任务（零开销基线） |
| **Baseline** | NoOp | 截断至 2000 chars | 无 | 3-5 轮中等任务 |
| **Context Mode** | InMemory | 旧消息压缩为引用 | ✅ | 5+ 轮复杂迭代任务 |

---

## 🔌 Agent SDK (Builder Pattern)

3 行代码创建自定义 Agent，支持自定义 Prompt + 多模型切换，向后兼容：

```python
from agent import AgentBuilder, InMemoryIndexStore

agent = (
    AgentBuilder()
    .llm(my_llm)                          # 任意 LangChain LLM
    .sandbox(my_sandbox)                   # Pyodide / 本地沙箱
    .system_prompt("You are a data analyst...")
    .index_store(InMemoryIndexStore())     # 启用上下文压缩
    .max_executions(10)
    .total_timeout(60)
    .build()
)
result = await agent.run("分析这份数据...")
```

---

## 📈 Eval Dashboard

### Jupyter Notebook

[eval_dashboard.ipynb](eval_dashboard.ipynb) — 10 个可视化 Section：

| Section | 内容 |
|---------|------|
| 1-2 | 数据加载 + 三模式总体指标对比 |
| 3 | Token 增长曲线（round_token_history 折线叠加） |
| 4 | 用户体感指标（端到端耗时、LLM 延迟、交互轮次） |
| 5 | 任务维度热力图（任务 × 模式） |
| 6 | Token 效率散点图（轮数 vs tokens/round） |
| 7 | 收敛漏斗（stop_reason 分布） |
| 8 | Context Mode 深度分析（fetch 调用分布、压缩比 vs 节省） |
| **9** | **跨模型分组对比**（tokens / rounds / success × model） |
| **10** | **模型效率象限图**（x=Token, y=完成率, 每点=model×mode） |

### 多模型横评

```bash
# 同一 benchmark、不同模型对比
python main.py --mode context_mode --model qwen-plus  --task-file ... --log-file logs/cm_qwen_plus.json
python main.py --mode context_mode --model qwen-turbo --task-file ... --log-file logs/cm_turbo.json
python main.py --mode context_mode --model gpt-4o-mini --base-url https://api.openai.com/v1 --api-key sk-xxx --task-file ... --log-file logs/cm_gpt4o.json
```

> Dashboard Section 9-10 在检测到多模型数据时自动生成跨模型对比图表。

---

## 🎯 用户场景决策

```
任务预估轮数？
├── 1-2 轮（简单计算/查询）→ Native Mode（零开销，最低延迟）
├── 3-5 轮（中等复杂度）  → Baseline Mode（截断防膨胀）
└── 5+ 轮（迭代调试）    → Context Mode（Token ↓50-83%）
```

| 角色 | 典型任务 | 推荐模式 |
|------|----------|----------|
| 🧑‍💻 前端实习生 | 写一个排序算法 | Native |
| 👩‍🔬 数据科学家 | 高斯消元解方程 | Context Mode |
| 🧑‍🏫 CS 教师 | 比较 5 种排序算法性能 | Context Mode |
| 👨‍💼 技术管理者 | 控制 API 每月成本 | Context Mode |

---

## 🔧 快速开始

```bash
# 1. 配置
cp .env.example .env  # 设置 DASHSCOPE_API_KEY

# 2. 运行 Agent
docker-compose run --rm sandbox python -m agent "计算 1 到 100 的和"

# 3. 三模式实验
for mode in native baseline context_mode; do
  python main.py --mode $mode \
    --task-file experiment_tasks/benchmark_tasks_subset5.txt \
    --log-file logs/${mode}.json
done

# 4. 查看 Eval Dashboard
jupyter notebook eval_dashboard.ipynb
```

---

## 📚 文档

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 开发指南：架构、命令、依赖、SDK、多模型横评 |
| [agent_docs/](agent_docs/) | 详细文档：系统设计、CLI 参考、测试、故障排除 |
| [architecture.md](architecture.md) | 系统架构与数据流图 |
| [EVOLUTION_PLAN.md](EVOLUTION_PLAN.md) | 四阶段演进计划（Phase 1-4） |

---

## 技术栈

- **LangGraph** — 状态图工作流编排
- **Pyodide (WebAssembly)** — 浏览器内 Python 沙箱执行
- **LangChain + OpenAI-compatible** — 多模型接入
- **Pandas + Matplotlib + Jupyter** — Eval 数据分析与可视化

---

## 许可证

MIT
