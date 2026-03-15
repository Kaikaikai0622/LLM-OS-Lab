# LangGraph 沙箱Agent

> **上下文管理的代码执行代理** —— 在经历了上一次的多Agent Orchestration失败后，我回过头探索单Agent的能力边界，基于目前主流编程Agent的核心痛点--上下文工程，产出一个做减法的 AI 编程Agent。

基于 LangGraph 构建，只做好一件事：在安全的 Pyodide（WebAssembly）沙箱中运行 Python 代码，并通过智能上下文压缩，将多轮任务中的 LLM Token 消耗最多降低 83%。没有多余的抽象层。我相信目前最强的单体Agent还远远没有触及（Openclaw还不足够），上下文工程是这个发展过程中的核心难点之一，本项目作为该痛点的众多解决思路之一的试验，同时作为我对“Agent是围绕LLM构建的操作系统”（Agent Harness）这一技术理念的践行和学习。

## 项目背景

当 LLM 代理迭代编写和执行代码时，每轮工具输出都会累积到对话上下文中。这导致**提示词 Token 线性增长** —— 降低响应质量、增加延迟并提高 API 成本。

本项目实现了三种上下文管理策略并进行基准测试：

| 策略 | 工作原理 | 适用场景 |
|------|-------------|----------|
| **原生模式** | 完整输出，无压缩 | 短任务（1-2 轮） |
| **基线模式** | 固定字符长度截断输出 | 中等任务 |
| **上下文模式** | 摘要压缩 + 执行索引 + 按需检索 | 复杂任务（5+ 轮） |

## 核心结果

在 4 个编码任务上的基准测试（斐波那契、高斯消元、数值积分、排序算法比较）：

| 指标 | 原生模式 | 基线模式 | 上下文模式 |
|--------|--------|----------|--------------|
| **排序任务 Token** | 130,320 | 453,936 | **22,766（降低 83%）** |
| **排序任务轮数** | 14（达到上限） | 25（达到上限） | **4（收敛完成）** |
| **高斯消元 Token** | 12,803 | 12,150 | **6,147（降低 52%）** |
| **平均收敛率** | 4 个任务中完成 3 个 | 4 个任务中完成 2 个 | **4 个任务全部完成** |
| **最大提示词 Token（排序）** | 15,203 | 33,173 | **6,018** |

**核心洞察**：上下文模式的开销（第 1 轮额外约 40% Token）在 2-3 轮内即可收回。在复杂迭代任务上，它实现了显著更低的总成本和更高的任务完成率。

## 功能特性

- **沙箱执行** —— Python 代码在 Pyodide（WebAssembly）中运行，与主机完全隔离
- **LangGraph StateGraph 工作流** —— 具备条件工具调用能力的结构化代理循环
- **三种上下文策略** —— 原生 / 基线 / 上下文模式，可通过 CLI 标志切换
- **执行索引** —— 结果以 UUID 键值存储；LLM 接收压缩摘要
- **按需详情检索** —— `fetch_execution_detail` 工具让 LLM 在需要时获取完整输出
- **结构化错误提取** —— 基于正则的 `error_type`、`error_message`、`error_line` 提取
- **旧消息压缩** —— 历史 ToolMessage + AIMessage 内容被替换为引用
- **每轮 Token 追踪** —— `prompt_tokens` / `completion_tokens` 每轮记录用于分析
- **总超时控制** —— 代理级超时防止执行失控
- **实验框架** —— `main.py` 运行多任务基准测试，支持所有 3 种模式的 JSON 日志记录
- **OpenAI 兼容** —— 兼容任何 OpenAI 兼容 API（已在阿里云 DashScope 上测试）
- **Docker 就绪** —— 完整的容器化环境，支持实时日志流

## 快速开始

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env，设置您的 API 密钥
```

`.env` 中必填项：
```bash
DASHSCOPE_API_KEY=sk-your-api-key
```

### 2. 运行

**Docker（推荐）：**

```bash
docker-compose up --build

# 运行代理
docker-compose run --rm sandbox python -m agent "计算 1 到 100 的和"

# 带选项运行
docker-compose run --rm sandbox python -m agent "求解 5x5 线性方程组" \
  --max-executions 10 --verbose
```

**本地运行：**

```bash
pip install -r requirements.txt
python -m agent "计算 1 到 100 的和"
```

### 3. 运行实验

```bash
# 在基准任务上比较所有 3 种模式
docker-compose run --rm sandbox python main.py \
  --mode native \
  --task-file experiment_tasks/benchmark_tasks_subset5.txt \
  --log-file logs/native.json

docker-compose run --rm sandbox python main.py \
  --mode baseline \
  --task-file experiment_tasks/benchmark_tasks_subset5.txt \
  --log-file logs/baseline.json

docker-compose run --rm sandbox python main.py \
  --mode context_mode \
  --task-file experiment_tasks/benchmark_tasks_subset5.txt \
  --log-file logs/context_mode.json
```

### 4. 运行测试

```bash
docker-compose run --rm sandbox python tests/smoke_e2e.py
docker-compose run --rm sandbox python tests/smoke_phase3_multi_toolcalls.py
docker-compose run --rm sandbox python tests/smoke_phase3_total_timeout.py
```

## 上下文模式工作原理

```
第 1 轮：LLM 生成代码 → 沙箱执行 → 完整输出索引 →
          压缩摘要（含结构化错误）返回给 LLM

第 2+ 轮：旧 ToolMessage 压缩为 "[execution_id: abc123] 使用 fetch_execution_detail"
          旧 AIMessage 压缩为 "[上一轮推理已压缩]"
          执行历史摘要作为 SystemMessage 注入
          LLM 只看到最近的上下文 + 历史概览

按需调用：LLM 调用 fetch_execution_detail(execution_id) 检索特定历史输出
```

这使得提示词窗口无论轮数多少都保持有界，同时通过索引保留对所有历史数据的访问。

## 项目结构

```
├── agent/                    # 代理核心
│   ├── agent.py             # SandboxAgent —— 编排与公共 API
│   ├── workflow.py          # LangGraph StateGraph —— 节点、边、压缩
│   ├── tools.py             # 工具实现 —— 执行、获取、读/写
│   ├── index_store.py       # InMemoryIndexStore / NoOpIndexStore
│   ├── schemas.py           # AgentState, ExecutionRecord, ToolResult
│   ├── prompts.py           # PromptBuilder —— 基础 + 上下文模式模板
│   ├── history_utils.py     # 执行历史摘要构建器
│   └── __main__.py          # CLI 入口点
├── main.py                  # 实验运行器（3 模式基准测试框架）
├── experiment_tasks/         # 基准任务文件
├── logs/                     # 实验结果（JSON）
├── tests/                    # 冒烟测试（阶段 1-4、多工具、超时）
├── sandbox_wrapper.py       # Pyodide stdout 换行符修复
├── Dockerfile               # Python 3.11 + Deno + langchain-sandbox
├── docker-compose.yml       # 带日志流的容器配置
└── .env.example             # 环境变量模板
```

## CLI 模式

```bash
# 原生模式 —— 完整输出，无压缩（基线上限）
python -m agent "task" --no-index --summary-max-chars 999999

# 基线模式 —— 仅输出截断
python -m agent "task" --no-fetch-tool

# 上下文模式 —— 完整流程（默认）
python -m agent "task"
```

| 标志 | 作用 |
|------|--------|
| `--no-index` | 禁用执行索引（原生模式） |
| `--no-fetch-tool` | 禁用 fetch_execution_detail（基线模式） |
| `--max-executions N` | 最大工具调用轮数 |
| `--total-timeout S` | 代理级超时（秒） |
| `--summary-max-chars N` | 输出摘要最大字符数 |
| `--verbose` | 显示每轮执行详情 |
| `--quiet` | 隐藏中间输出 |
| `--backend local\|pyodide` | 执行后端 |

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|----------|----------|---------|-------------|
| `DASHSCOPE_API_KEY` | 是 | — | OpenAI 兼容 API 密钥 |
| `LLM_MODEL` | 否 | qwen-plus | 模型名称 |
| `LLM_BASE_URL` | 否 | DashScope | API 基础 URL |
| `AGENT_MAX_EXECUTIONS` | 否 | 10 | 最大执行轮数 |
| `AGENT_TOTAL_TIMEOUT_SECONDS` | 否 | 60 | 总超时（秒） |
| `AGENT_TOOL_TIMEOUT_SECONDS` | 否 | 15 | 每个工具超时 |
| `AGENT_SUMMARY_MAX_CHARS` | 否 | 500 | 摘要截断限制 |

## 改进与路线图

### 已完成

- **结构化错误提取** —— 从 stderr 提取错误类型、消息和行号，包含在每个工具摘要中，减少不必要的 `fetch_execution_detail` 调用
- **引导式工具描述** —— `execute_python` 和 `fetch_execution_detail` 包含明确的使用指导（何时使用、何时不使用）
- **旧消息压缩** —— 前面轮次的 ToolMessage 和 AIMessage 内容被替换为紧凑引用
- **执行历史注入** —— 带执行历史摘要的 SystemMessage 帮助 LLM 利用过去的尝试
- **每轮 Token 追踪** —— 支持跨模式的精确 Token 增长曲线分析
- **3 模式实验框架** —— 可复现的基准测试框架，支持 JSON 日志记录

### 下一步

- **索引查询优化** —— 改进 `fetch_execution_detail` 检索相关性，使 LLM 首次调用即可获得正确的历史数据
- **扩展基准测试** —— 设计需要 8+ 执行轮次的任务，充分展示上下文模式的平稳特性
- **Token 增长可视化** —— 从实验日志生成每轮 Token 曲线

## 技术栈

- **Python 3.11** —— 运行时
- **LangChain** / **LangGraph** —— 代理框架与状态图工作流
- **langchain-sandbox** —— Pyodide WebAssembly 沙箱
- **Pyodide** —— 基于 WebAssembly 的浏览器内 Python
- **Deno** —— Pyodide 执行的 JavaScript 运行时
- **Docker** —— 容器化开发与部署

## 文档

| 文档 | 用途 |
|----------|---------|
| [architecture.md](architecture.md) | 系统架构与数据流 |
| [CLAUDE.md](CLAUDE.md) | AI 辅助开发开发者指南 |
| [agent_docs/](agent_docs/) | 详细文档：代理系统、沙箱、测试、故障排除 |

## 许可证

MIT
