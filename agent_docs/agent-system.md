# Agent 系统详解

Agent 系统的核心组件和工作原理。

## 架构概述

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│   LLM API   │    │  Agent Core  │    │   Sandbox    │
│  (主机上)   │◄──►│  (LangGraph) │◄──►│ (Pyodide)    │
└─────────────┘    └──────────────┘    └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  结果索引    │
                   │ (内存/预留   │
                   │  持久化接口) │
                   └──────────────┘
```

## 核心组件

### SandboxAgent

主 Agent 类，封装 LLM、沙箱和索引存储。

```python
from agent import SandboxAgent, InMemoryIndexStore
from sandbox_wrapper import FixedPyodideSandbox

agent = SandboxAgent(
    llm=llm_callable,           # LLM 调用函数
    sandbox=FixedPyodideSandbox(),  # 沙箱实例
    index_store=InMemoryIndexStore(),  # 索引存储
    max_executions=10,          # 最大执行次数
    total_timeout_seconds=60,   # 总超时时间（秒）
    verbose=True,               # 是否打印诊断日志
)

result = await agent.run("计算1到100的和")
print(result.answer)            # 最终回答
print(result.execution_count)   # 工具执行次数
print(result.stop_reason)       # 停止原因: "max_executions" | "total_timeout" | "no_tool_calls"
print(result.last_execution_id) # 最后执行ID
```

### LangGraph StateGraph 工作流

真正的 LangGraph StateGraph 管理 Agent 的多轮执行：

```
START → agent_node → [condition] ─→ tool_executor ─→ agent_node ─┐
              ↓                         ↓                          │
            END (无 tool_calls)    finalizer ←─────────────────────┘
```

节点说明：
- `agent_node`: LLM 决策节点，产出 AIMessage（可能含 tool_calls）
- `tool_executor`: 工具执行节点，**顺序执行全部 tool_calls**
- `finalizer`: 最终节点，提取 final_answer 和 stop_reason
- `should_continue`: 条件边，判断继续执行或结束

**多 tool_calls 支持**：
- 单轮可包含多个 tool_calls
- 按原始顺序顺序执行
- execution_count 按实际调用次数累计

**停止条件优先级**：
1. `total_timeout` - 总超时（最高优先级）
2. `max_executions` - 达到最大执行次数
3. `no_tool_calls` - LLM 返回无 tool_calls 的消息

### 索引存储

抽象接口支持多种存储后端：

```python
from agent import IndexStore, InMemoryIndexStore

class IndexStore(ABC):
    @abstractmethod
    def save(self, execution_result: dict) -> str:
        """保存执行结果，返回 execution_id"""

    @abstractmethod
    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        """根据 ID 获取完整记录"""

    @abstractmethod
    def latest(self, limit: int = 5) -> list[ExecutionRecord]:
        """获取最近 N 条记录"""
```

当前实现：
- `InMemoryIndexStore`: 内存存储（最小实现）
- 预留：`FileIndexStore`（文件持久化）、`VectorIndexStore`（向量检索）

**重要注意**：`InMemoryIndexStore` 定义了 `__len__`，空存储在布尔上下文为 `False`：

```python
# 错误 - 空存储会创建新实例
self.index_store = index_store or InMemoryIndexStore()

# 正确
self.index_store = index_store if index_store is not None else InMemoryIndexStore()
```

### 工具执行

沙箱工具遵循 "执行 → 索引 → 摘要" 模式：

```python
from agent.tools import execute_python

result = await execute_python(
    code="print(sum(range(1, 101)))",
    sandbox=sandbox,
    index_store=store,
)
# result.execution_id - 执行ID
# result.status - 执行状态
# result.summary - 压缩摘要
```

摘要生成策略：
- stdout 截断到指定字符数
- stderr 单独截断
- 包含状态、输出长度等元数据

## 数据模型

### AgentState

LangGraph StateGraph 状态定义：

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # 对话历史，使用 add_messages 归约
    execution_count: int              # 当前工具执行次数（按调用次数累计）
    max_executions: int               # 最大执行次数限制
    last_execution_id: Optional[str]  # 最近一次执行ID
    final_answer: Optional[str]       # 最终回答
    started_at: Optional[float]       # Agent 启动时间（monotonic 时间戳）
    total_timeout_seconds: Optional[float]  # 总超时时间（秒）
    stop_reason: Optional[str]        # 停止原因
```

### ExecutionRecord

代码执行记录：

```python
@dataclass
class ExecutionRecord:
    execution_id: str
    status: str                    # "success" | "error" | "timeout"
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    execution_time: float = 0.0
    created_at: str
```

### ToolResult

工具执行结果（返回给 LLM）：

```python
@dataclass
class ToolResult:
    execution_id: str
    status: str
    summary: str                   # 压缩后的摘要
    stdout_chars: int
    stderr_chars: int
```

## 多轮执行控制

- **最大执行次数限制**（`max_executions`）：默认 10 次，按实际工具调用次数累计
- **总超时控制**（`total_timeout_seconds`）：默认 60 秒，优先级高于 max_executions
- **停止原因**（`stop_reason`）：
  - `"total_timeout"` - 总超时触发（最高优先级）
  - `"max_executions"` - 达到最大执行次数
  - `"no_tool_calls"` - LLM 返回无 tool_calls 的消息（正常结束）
- **循环检测**：相同工具调用参数检测

## StateGraph 迁移说明（2026-03-14）

workflow.py 已从 `while True` 循环重构为真正的 LangGraph StateGraph：

1. **真实图编排**：使用 `StateGraph` 定义节点和边
2. **条件边**：`should_continue` 根据超时、执行次数、tool_calls 决定走向
3. **多 tool_calls 支持**：`tool_executor` 顺序执行全部 tool_calls
4. **标准化处理**：支持多种 tool_call 格式（LangChain / OpenAI）

## 文件清单

- `agent/agent.py` - SandboxAgent 主类
- `agent/workflow.py` - LangGraph 工作流定义
- `agent/tools.py` - 沙箱工具实现
- `agent/index_store.py` - 索引存储系统
- `agent/schemas.py` - 数据模型定义
- `agent/prompts.py` - 提示词模板
- `agent/__main__.py` - CLI 入口
