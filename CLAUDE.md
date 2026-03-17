# CLAUDE.md

## Project Overview

**LangChain Sandbox Agent** — A context-managed code execution agent built on LangGraph, with sandboxed Python execution via Pyodide (WebAssembly). The project implements and benchmarks three context management strategies (Native/Baseline/Context Mode) to measure token efficiency in multi-round tool-calling workflows.

**Core Value Proposition**: Context Mode reduces LLM token consumption by up to 83% on complex iterative tasks while maintaining 100% task convergence rate.

## Architecture

### Three Modes

| Mode | Index | Compression | Fetch Tool | Summary | Use Case |
|------|-------|-------------|------------|---------|----------|
| **Native** | NoOp | OFF | OFF | Full output (999999 chars) | Upper bound / simple tasks |
| **Baseline** | NoOp | OFF | OFF | Truncated (2000 chars) | Medium tasks |
| **Context Mode** | InMemory | ON | ON | Compressed + indexed | Complex multi-round tasks |

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `SandboxAgent` | `agent/agent.py` | Public API, orchestration, mode detection |
| `AgentBuilder` | `agent/builder.py` | SDK Builder Pattern — fluent API for custom Agent construction |
| `AgentWorkflow` | `agent/workflow.py` | LangGraph StateGraph, node implementations, message compression |
| Tool implementations | `agent/tools.py` | `execute_python`, `fetch_execution_detail`, `read_file`, `write_file` |
| `PromptBuilder` | `agent/prompts.py` | System prompt templates (base + context mode) |
| Index storage | `agent/index_store.py` | `InMemoryIndexStore` / `NoOpIndexStore` |
| History utils | `agent/history_utils.py` | `build_execution_summary()` for history injection |
| Data models | `agent/schemas.py` | `AgentState`, `ExecutionRecord`, `ToolResult` |
| CLI entry | `agent/__main__.py` | Argument parsing, LLM creation, config validation |
| Experiment runner | `main.py` | Multi-task benchmark harness, 3-mode + multi-model comparison |
| Eval Dashboard | `eval_dashboard.ipynb` | Jupyter Notebook — metrics visualization + cross-model comparison |

## Development Environment

### Docker Setup

```bash
# Build and run
docker-compose up --build

# Run Agent
docker-compose run --rm sandbox python -m agent "计算 1 到 100 的和"

# Run E2E test
docker-compose run --rm sandbox python tests/smoke_e2e.py

# Interactive shell
docker-compose run --rm sandbox bash
```

### Docker Observability (Real-time Logging)

The Docker environment is configured with `PYTHONUNBUFFERED=1` for real-time log output.

**Run experiment with live output:**
```bash
docker-compose run --rm sandbox python main.py \
  --mode context_mode \
  --task-file experiment_tasks/benchmark_tasks_subset5.txt \
  --log-file logs/cm_$(date +%Y%m%d_%H%M%S).json
```

### Local Development

```bash
pip install -r requirements.txt
python -m agent "2+2等于多少"
```

## Key Commands

```bash
# Quick test
python -m agent "2+2等于多少"

# With options
python -m agent "计算1到100的和" --max-executions 5 --verbose

# Three modes via CLI
python -m agent "task" --no-index --summary-max-chars 999999  # Native
python -m agent "task" --no-fetch-tool                         # Baseline
python -m agent "task"                                         # Context Mode (default)

# Specify model/provider via CLI (overrides env vars)
python -m agent "task" --model qwen-turbo
python -m agent "task" --model gpt-4o-mini --base-url https://api.openai.com/v1 --api-key sk-xxx

# Smoke tests
docker-compose run --rm sandbox python tests/smoke_e2e.py
docker-compose run --rm sandbox python tests/smoke_phase3_multi_toolcalls.py
docker-compose run --rm sandbox python tests/smoke_phase3_total_timeout.py

# Run 3-mode experiment
python main.py --mode native --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/native.json
python main.py --mode baseline --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/baseline.json
python main.py --mode context_mode --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/cm.json

# Multi-model cross-evaluation
python main.py --mode context_mode --model qwen-plus  --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/cm_qwen_plus.json
python main.py --mode context_mode --model qwen-turbo --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/cm_qwen_turbo.json
python main.py --mode context_mode --model gpt-4o-mini --base-url https://api.openai.com/v1 --api-key sk-xxx --task-file ... --log-file logs/cm_gpt4o.json
```

## Key Dependencies

- `langchain>=0.3,<0.4` — Core framework
- `langchain-core>=0.3,<0.4` — Message types, protocols
- `langgraph>=0.4.3,<0.5` — State graph workflow
- `langchain-sandbox>=0.0.6` — Pyodide sandbox wrapper
- `langchain-openai>=0.3,<0.4` — OpenAI-compatible LLM client
- `python-dotenv>=1.0,<2.0` — .env loading

## Project Structure

```
my-sandbox-demo/
├── agent/                  # Agent core implementation
│   ├── agent.py           # SandboxAgent — public API & orchestration
│   ├── builder.py         # AgentBuilder — SDK Builder Pattern (Phase 2)
│   ├── workflow.py        # LangGraph StateGraph — nodes, edges, compression
│   ├── tools.py           # Tool implementations + structured error extraction
│   ├── index_store.py     # InMemoryIndexStore / NoOpIndexStore
│   ├── schemas.py         # AgentState, ExecutionRecord, ToolResult
│   ├── prompts.py         # Prompt templates (base + context mode)
│   ├── history_utils.py   # Execution history summary builder
│   └── __main__.py        # CLI entry point (supports --model/--base-url/--api-key)
├── main.py                # Experiment runner (3-mode + multi-model benchmark)
├── eval_dashboard.ipynb   # Eval Dashboard — metrics visualization + cross-model comparison
├── experiment_tasks/      # Benchmark task files
├── logs/                  # Experiment results (JSON, includes model field)
├── tests/                 # Smoke tests
├── agent_docs/            # Detailed documentation
├── sandbox_wrapper.py     # Pyodide stdout newline fix
├── architecture.md        # System architecture diagram
└── README.md              # Product documentation
```

## Critical Implementation Notes

### Context Mode Pipeline
1. **Tool execution**: Code runs in Pyodide → result indexed with UUID → compressed summary returned
2. **Error extraction**: Regex parses stderr for `error_type`, `error_message`, `error_line`
3. **Old message compression**: ToolMessages beyond `keep_recent=3` → `"[execution_id: abc] Use fetch_execution_detail"`; matching AIMessages → `"[Previous round reasoning compressed]"`
4. **History injection**: `build_execution_summary()` adds recent execution overview as SystemMessage
5. **On-demand retrieval**: LLM can call `fetch_execution_detail(execution_id)` when summary is insufficient

### Mode Detection
```python
# In SandboxAgent.__init__:
self.compress_mode = not isinstance(self.index_store, NoOpIndexStore)
self.has_fetch_tool = has_fetch_tool if has_fetch_tool is not None else self.compress_mode
```

### Agent SDK (Builder Pattern)

`AgentBuilder` provides a fluent API for constructing custom Agents without touching internals:

```python
from agent import AgentBuilder, InMemoryIndexStore

agent = (
    AgentBuilder()
    .llm(my_llm)                                    # Required
    .sandbox(my_sandbox)                             # Required
    .system_prompt("You are a data analyst...")      # Optional custom prompt
    .index_store(InMemoryIndexStore())               # Optional, enables context compression
    .max_executions(10)                              # Optional
    .total_timeout(60)                               # Optional
    .build()                                         # → SandboxAgent
)
result = await agent.run("分析这份数据...")
```

Key: `SandboxAgent` now accepts an optional `custom_system_prompt` parameter (used by Builder). When set, it overrides the default `PromptBuilder.build_system_prompt()`.

### Multi-Model Evaluation

Both `agent/__main__.py` and `main.py` support `--model`, `--base-url`, `--api-key` CLI arguments.

**Priority**: CLI args > environment variables > defaults.

The experiment JSON log now includes a `"model"` field, and `eval_dashboard.ipynb` auto-detects multiple models to generate cross-model comparison charts (Section 9-10).

### Known Gotchas
- `InMemoryIndexStore` evaluates to `False` when empty — always use `is not None` check
- `FixedPyodideSandbox` is required to fix stdout newline loss in `@langchain/pyodide-sandbox`
- LLM tool binding must happen AFTER tool list is determined (mode-dependent)

## Environment Variables

Create `.env` file:

```bash
DASHSCOPE_API_KEY=sk-xxx           # Required
LLM_MODEL=qwen-plus                # Optional
LLM_BASE_URL=...                   # Optional
AGENT_MAX_EXECUTIONS=10            # Optional
AGENT_TOTAL_TIMEOUT_SECONDS=60     # Optional
AGENT_TOOL_TIMEOUT_SECONDS=15      # Optional
AGENT_SUMMARY_MAX_CHARS=500        # Optional
AGENT_ALLOW_NET=true               # Optional
```