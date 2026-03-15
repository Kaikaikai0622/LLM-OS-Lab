# Architecture

## System Overview

LangChain Sandbox Agent is a context-managed code execution system built on LangGraph. It implements three context management strategies for multi-round LLM tool-calling workflows, with Python execution sandboxed in Pyodide (WebAssembly).

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              User / CLI                                  │
│                         python -m agent "task"                           │
├──────────────────────────────────────────────────────────────────────────┤
│                          agent/__main__.py                               │
│    Mode selection (--no-index / --no-fetch-tool / default)              │
│    LLM creation, config validation, tool binding                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    SandboxAgent (agent.py)                         │  │
│  │  • compress_mode detection (index_store type)                     │  │
│  │  • has_fetch_tool toggle                                          │  │
│  │  • AgentResult: answer, tokens, stop_reason, elapsed              │  │
│  └────────────────────┬───────────────────────────────────────────────┘  │
│                       │                                                  │
│  ┌────────────────────▼───────────────────────────────────────────────┐  │
│  │               AgentWorkflow (workflow.py)                         │  │
│  │                  LangGraph StateGraph                             │  │
│  │                                                                    │  │
│  │  ┌─────────┐     ┌──────────────┐     ┌───────────┐              │  │
│  │  │ agent   │────▶│ tool_executor │────▶│ agent     │──┐           │  │
│  │  │ _node   │     │              │     │ _node     │  │ (loop)    │  │
│  │  └─────────┘     └──────────────┘     └───────────┘  │           │  │
│  │       │                                      │        │           │  │
│  │       │ no tool_calls / timeout              │        │           │  │
│  │       ▼                                      ▼        │           │  │
│  │  ┌───────────┐                      ┌──────────────┐  │           │  │
│  │  │ finalizer │◀─────────────────────│ compress_old │◀─┘           │  │
│  │  │           │                      │ _messages    │              │  │
│  │  └───────────┘                      └──────────────┘              │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                       │                        │                         │
│            ┌──────────▼──────────┐  ┌──────────▼──────────┐             │
│            │   IndexStore        │  │   PromptBuilder     │             │
│            │ InMemory / NoOp     │  │ base + context mode │             │
│            └──────────┬──────────┘  └─────────────────────┘             │
│                       │                                                  │
├───────────────────────▼──────────────────────────────────────────────────┤
│                         Tool Layer (tools.py)                            │
│  execute_python │ fetch_execution_detail │ read_file │ write_file       │
├──────────────────────────────────────────────────────────────────────────┤
│                    sandbox_wrapper.py                                     │
│              FixedPyodideSandbox (newline fix)                           │
├──────────────────────────────────────────────────────────────────────────┤
│                     langchain-sandbox                                     │
│              (Python wrapper for Pyodide sandbox)                        │
├──────────────────────────────────────────────────────────────────────────┤
│                          Deno Runtime                                    │
│          @langchain/pyodide-sandbox (JSR package)                       │
├──────────────────────────────────────────────────────────────────────────┤
│                         Pyodide (WASM)                                   │
│            Python 3.12 interpreter in WebAssembly                       │
│            Isolated execution — no host filesystem access               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Three Context Management Modes

### Data Flow Comparison

```
                    Native                Baseline              Context Mode
                    ──────                ────────              ────────────
Tool Output     →   Full (999999 chars)   Truncated (2000)      Compressed (2000)
Index Storage   →   NoOp (discarded)      NoOp (discarded)      InMemory (UUID-keyed)
Old Messages    →   Kept as-is            Kept as-is            Compressed to refs
History Summary →   None                  None                  Injected (SystemMsg)
Fetch Tool      →   Not available         Not available         Available on-demand
Token Growth    →   Linear ↗              Linear (slower) ↗     Plateau ━
```

### Mode Activation

```python
# In SandboxAgent.__init__:
self.compress_mode = not isinstance(self.index_store, NoOpIndexStore)
self.has_fetch_tool = has_fetch_tool if has_fetch_tool is not None else self.compress_mode

# CLI flags:
#   Native:       --no-index --summary-max-chars 999999
#   Baseline:     --no-fetch-tool
#   Context Mode:  (default)
```

---

## Context Mode Pipeline

### Per-Round Execution Flow

```
                    ┌─────────────────────────────┐
                    │     agent_node (LLM call)    │
                    │  • inject history summary    │
                    │  • compress old messages     │
                    │  • call LLM with messages    │
                    │  • track token usage         │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │      tool_executor           │
                    │  For each tool_call:         │
                    │  1. Run code in Pyodide      │
                    │  2. Extract structured error  │
                    │  3. Index full result (UUID)  │
                    │  4. Return compressed summary │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   compress_old_messages       │
                    │  • Keep recent 3 ToolMessages │
                    │  • Older → "[execution_id:    │
                    │    abc] Use fetch for detail"  │
                    │  • Matching AIMessages →       │
                    │    "[Reasoning compressed]"    │
                    └──────────────┬───────────────┘
                                   │
                              Loop back to
                              agent_node
```

### Message Window After Round 5

```
SystemMessage:  "You are a coding agent..."
SystemMessage:  "[Execution History Summary] Round 1: ✓ ... Round 4: ✗ ..."
HumanMessage:   "Sort 3 arrays using different algorithms..."
AIMessage:      "[Previous round reasoning compressed]"          ← Round 1 (compressed)
ToolMessage:    "[execution_id: a1b2] Use fetch_execution..."   ← Round 1 (compressed)
AIMessage:      "[Previous round reasoning compressed]"          ← Round 2 (compressed)
ToolMessage:    "[execution_id: c3d4] Use fetch_execution..."   ← Round 2 (compressed)
AIMessage:      { full code + reasoning }                        ← Round 3 (recent, kept)
ToolMessage:    { full execution output }                        ← Round 3 (recent, kept)
AIMessage:      { full code + reasoning }                        ← Round 4 (recent, kept)
ToolMessage:    { full execution output }                        ← Round 4 (recent, kept)
AIMessage:      { full code + reasoning }                        ← Round 5 (current)
ToolMessage:    { full execution output }                        ← Round 5 (current)
```

---

## Structured Error Extraction

When code execution fails, `tools.py` extracts structured error information via regex:

```
stderr: "Traceback (most recent call last):\n  File ..., line 5\n    ...\nNameError: name 'x' is not defined"
                                        ↓
ToolMessage summary includes:
  error_type: NameError
  error_message: name 'x' is not defined
  error_line: 5
```

This enables the LLM to diagnose and fix errors directly from the compressed summary, without needing to call `fetch_execution_detail`.

---

## Execution Indexing

```
execute_python("code")
       │
       ▼
  Pyodide sandbox
       │
       ▼
  ExecutionRecord {
    execution_id: "a1b2c3d4..."   ← UUID hex
    status: "success" | "error"
    stdout: "..."                   ← Full output
    stderr: "..."                   ← Full errors
    execution_time: 1.23
    error_type: "NameError"         ← Structured (if error)
    error_message: "..."            ← Structured (if error)
    error_line: 5                   ← Structured (if error)
    created_at: "2026-03-15T..."
  }
       │
       ├──▶ InMemoryIndexStore.save(record)    ← Context Mode
       │    (UUID → full record, retrievable)
       │
       └──▶ NoOpIndexStore.save(record)        ← Native / Baseline
            (UUID generated, data discarded)
       │
       ▼
  Compressed summary → ToolMessage
  (max 2000 chars + error fields)
```

---

## Experiment Framework

```
main.py
  │
  ├── Parse --mode (native | baseline | context_mode)
  ├── Parse --task-file (one task per line)
  ├── Configure agent with mode-specific flags
  │
  └── For each task:
        ├── Create fresh SandboxAgent + IndexStore
        ├── Run agent.run(task)
        ├── Collect: tokens, rounds, elapsed, stop_reason
        ├── Capture round_token_history (per-round breakdown)
        └── Append to JSON log file
```

Output log format:
```json
{
  "task": "Sort 3 arrays...",
  "execution_count": 4,
  "stop_reason": "no_tool_calls",
  "llm_total_tokens": 22766,
  "max_prompt_tokens": 6018,
  "elapsed_seconds": 32.35,
  "round_token_history": [
    {"round": 0, "prompt_tokens": 1563, "completion_tokens": 800, "total_tokens": 2363},
    ...
  ]
}
```

---

## Sandbox Stack

### Pyodide Execution Pipeline

```
PyodideSandbox.execute(code)
    │
    ├─▶ _build_command()           # Build deno command
    │       ├─ permissions (allow_net, allow_read, etc.)
    │       └─ code (user Python code)
    │
    ├─▶ asyncio.create_subprocess_exec()  # Launch Deno process
    │
    ├─▶ process.communicate()      # Wait for completion
    │
    └─▶ json.loads(stdout)         # Parse JSON result
            ├─ result.stdout  (⚠ newlines lost → FixedPyodideSandbox)
            ├─ result.stderr
            ├─ result.result
            └─ result.success
```

### Known Bug: Newline Loss

`@langchain/pyodide-sandbox` uses `output.join('')` instead of `output.join('\n')`, losing newlines in stdout/stderr. `FixedPyodideSandbox` in `sandbox_wrapper.py` applies heuristic newline recovery.

### Deno Permission Model

| Permission | Config | Purpose |
|------------|--------|---------|
| `--allow-net` | `True/List[str]` | Network access for pip |
| `--allow-read` | `node_modules` | Read Pyodide WASM files |
| `--allow-write` | `node_modules` | Write cache |
| `--allow-env` | `False` | No env access |
| `--allow-run` | `False` | No subprocess |
| `--allow-ffi` | `False` | No FFI |

---

## 数据流

### 代码执行数据流

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  User Code  │────▶│  Python Wrapper  │────▶│  Deno Subprocess│
│  (Python)   │     │  (pyodide.py)    │     │  (TypeScript)   │
└─────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  JSON Parse │◀────│  stdout capture  │◀────│  Pyodide WASM   │
│  (Result)   │     │  (with bug)      │     │  (Execution)    │
└─────────────┘     └──────────────────┘     └─────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                    FixedPyodideSandbox                       │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │ _count_prints() │───▶│ _split_pattern()│                 │
│  │  (code analysis)│    │  (heuristic)    │                 │
│  └─────────────────┘    └─────────────────┘                 │
│           │                      │                           │
│           ▼                      ▼                           │
│  ┌─────────────────────────────────────────┐                │
│  │      _fix_newlines()                    │                │
│  │  "Line1Line2" ──▶ "Line1\nLine2"       │                │
│  └─────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

### Session 持久化数据流 (Stateful Mode)

```
Execution 1                    Execution 2
    │                              │
    ▼                              ▼
┌──────────┐                ┌──────────┐
│  Code    │                │  Code    │
│  Run     │                │  Run     │
└────┬─────┘                └────┬─────┘
     │                           │
     ▼                           ▼
┌──────────┐                ┌──────────┐
│  dill    │───────────────▶│  dill    │
│  dump    │  session_bytes │  load    │
│  session │────────────────│  session │
└──────────┘                └──────────┘
     │                           │
     ▼                           ▼
┌──────────┐                ┌──────────┐
│  Return  │                │  Access  │
│  bytes   │                │  vars    │
└──────────┘                └──────────┘
```

---

## 性能特征

### 执行延迟分解

| 阶段 | 耗时 | 说明 |
|------|------|------|
| Deno 启动 | ~10ms | 可忽略 |
| JSR 包加载 | ~200ms | TypeScript 编译 |
| **Pyodide 初始化** | **~1.3s** | **主要瓶颈** |
| WASM 实例化 | ~500ms | 一次性 |
| Python 环境 | ~800ms | 标准库加载 |
| 代码执行 | ~50-200ms | 取决于代码 |
| **总计** | **~1.5-1.9s** | 每次执行 |

### 优化建议

1. **当前无法优化**: 每次执行都重新初始化 Pyodide（架构限制）
2. **Stateful 模式**: 变量持久化但性能更差 (~3.3s)，因序列化开销
3. **长期方案**: 等待上游实现 Pyodide 实例池复用

---

## 文件组织

```
my-sandbox-demo/
├── CLAUDE.md               # Claude Code 指导文档
├── architecture.md         # 本文件：架构文档
├── demo.py                 # 基础演示
├── sandbox_wrapper.py      # 换行符修复包装器
├── test_sandbox.py         # 功能验证测试
├── test_stateful.py        # Stateful 模式测试
├── Dockerfile              # 容器镜像定义
├── docker-compose.yml      # Docker Compose 配置
├── .devcontainer/
│   └── devcontainer.json   # VS Code Dev Container
└── node_modules/           # Deno 依赖缓存
    └── .deno/
        ├── pyodide@0.27.7/
        └── jsr/@langchain/pyodide-sandbox/
```

---

## 依赖关系

```
demo.py
  └─▶ langchain_sandbox.PyodideSandbox
        └─▶ deno run jsr:@langchain/pyodide-sandbox
              └─▶ npm:pyodide@0.27.7
                    └─▶ pyodide.asm.wasm

sandbox_wrapper.py
  └─▶ langchain_sandbox.PyodideSandbox
        └─▶ (same chain as above)
```

---

## 安全模型

### 沙箱隔离层级

1. **Process Isolation**: Deno 子进程隔离
2. **WASM Sandbox**: WebAssembly 内存安全
3. **Permission Model**: 显式权限控制 (net, read, write, etc.)
4. **No System Access**: 默认无文件系统/网络访问

### 威胁模型

| 威胁 | 防护 | 状态 |
|------|------|------|
| 恶意代码执行 | WASM 沙箱 | ✅ 安全 |
| 无限循环 | 超时机制 | ✅ 支持 |
| 内存耗尽 | V8 内存限制 | ✅ 支持 |
| 文件系统逃逸 | Deno 权限 | ✅ 默认禁用 |
| 网络攻击 | Deno 权限 | ✅ 默认禁用 |
