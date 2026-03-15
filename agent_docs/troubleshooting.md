# 常见问题

开发和使用过程中可能遇到的问题及解决方案。

## 关键实现注意事项

### InMemoryIndexStore Boolean Evaluation

**⚠️ Important**: `InMemoryIndexStore` defines `__len__`, so empty stores evaluate to `False`:

```python
# WRONG - creates new instance when store is empty
self.index_store = index_store or InMemoryIndexStore()

# CORRECT
self.index_store = index_store if index_store is not None else InMemoryIndexStore()
```

### LLM Tool Binding

LLM must bind tools to trigger tool calls:

```python
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool

tool = StructuredTool.from_function(...)

llm = ChatOpenAI(
    model="qwen-plus",
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
).bind_tools([tool])  # REQUIRED
```

### FixedPyodideSandbox

Always use `FixedPyodideSandbox` instead of raw `PyodideSandbox` to fix newline loss:

```python
from sandbox_wrapper import FixedPyodideSandbox

sandbox = FixedPyodideSandbox(allow_net=True)
```

---

## 配置问题

### DASHSCOPE_API_KEY 未设置

**错误**：
```
[CONFIG_ERROR] DASHSCOPE_API_KEY: 未设置，请检查 .env 文件或环境变量
```

**解决**：
```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 依赖未安装

**错误**：
```
ImportError: No module named 'langchain_openai'
```

**解决**：
```bash
pip install -r requirements.txt
```

## 运行时问题

### InMemoryIndexStore 布尔判断错误

**症状**：传入的 index_store 被忽略，创建了新的空实例

**原因**：`InMemoryIndexStore` 定义了 `__len__`，空存储在布尔上下文为 `False`

**解决**：使用 `is not None` 判断

```python
# 错误
self.index_store = index_store or InMemoryIndexStore()

# 正确
self.index_store = index_store if index_store is not None else InMemoryIndexStore()
```

### 工具调用未触发

**症状**：LLM 返回纯文本回答，没有调用工具

**原因**：LLM 未绑定工具

**解决**：使用 `.bind_tools()`

```python
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool

tool = StructuredTool.from_function(...)

llm = ChatOpenAI(
    model="qwen-plus",
    api_key=api_key,
    base_url=base_url,
).bind_tools([tool])  # 必须绑定工具
```

### 空代码错误

**错误**：
```
Error: Empty code provided
```

**原因**：`tool_call` 格式不匹配，无法正确提取代码参数

**解决**：在 workflow.py 中支持多种格式

```python
# 支持多种参数键名
arguments = tool_call.get("args", tool_call.get("arguments", {}))

# 支持字符串或字典
if isinstance(arguments, str):
    import json
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        args = {"code": arguments}
```

## 沙箱问题

### stdout 换行丢失

**症状**：
```python
print("line1")
print("line2")
# 输出: "line1line2"（没有换行）
```

**解决**：使用 `FixedPyodideSandbox`

```python
from sandbox_wrapper import FixedPyodideSandbox

sandbox = FixedPyodideSandbox(allow_net=True)
```

### 沙箱首次启动慢

**症状**：首次执行需要 ~8s

**原因**：Pyodide WebAssembly 运行时初始化

**解决**：这是正常现象，后续执行约 ~1.5-2s

## Docker 问题

### 路径错误

**错误**：
```
No such file or directory: 'd:/Code/my-sandbox-demo'
```

**原因**：Windows 路径格式问题

**解决**：在代码中自动检测项目根目录

```python
if os.path.exists("/app"):
    PROJECT_ROOT = "/app"
else:
    PROJECT_ROOT = str(Path(__file__).parent.parent)
```

## StateGraph 迁移相关问题（2026-03-14）

### LangGraph 未安装

**错误**：
```
ImportError: No module named 'langgraph'
```

**解决**：
```bash
pip install langgraph
```

### execution_count 语义变化

**症状**：测试失败，提示 execution_count 不符合预期

**原因**：StateGraph 迁移后，`execution_count` 从"按轮次"改为"按实际工具调用次数"统计

**旧行为**：3 轮 × 每轮 1 个 tool_call = execution_count: 3
**新行为**：单轮 3 个 tool_calls = execution_count: 3

**解决**：更新测试断言以匹配新语义

### stop_reason 为 None

**症状**：`result.stop_reason` 为 `None`，预期应为 `"no_tool_calls"`

**原因**：finalizer 节点未正确执行或状态未正确传递

**解决**：检查 workflow.py 中 finalizer 节点是否正确添加到 StateGraph

## 调试技巧

### 启用详细日志

```python
agent = SandboxAgent(
    llm=llm,
    sandbox=sandbox,
    index_store=store,
    max_executions=10,
    total_timeout_seconds=60,
    verbose=True,  # 打印诊断日志
)
```

### 检查执行记录

```python
result = await agent.run("计算 1+1")
print(f"执行次数: {result.execution_count}")
print(f"停止原因: {result.stop_reason}")
print(f"是否被限制: {result.stopped_by_limit}")

record = agent.get_execution_record(result.last_execution_id)
print(record.stdout)
print(record.stderr)
```

### 手动测试 LLM 连接

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="qwen-plus",
    api_key="sk-xxx",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
response = llm.invoke([{"role": "user", "content": "Hello"}])
print(response.content)
```

### 测试多 tool_calls 场景

```python
# 测试单轮多 tool_calls
result = await agent.run("同时计算 1+1 和 2+2")
# 如果 LLM 返回两个 tool_calls，execution_count 应为 2
print(f"执行次数: {result.execution_count}")
```

---

## Known Issues

1. **Newline Loss**: `@langchain/pyodide-sandbox` uses `join('')` instead of `join('\n')`
   - **Fix**: Use `FixedPyodideSandbox`

2. **Stateful Mode Slow**: ~3.3s vs ~1.5s for stateless
   - **Reason**: Pyodide re-initialization
   - **Fix**: Use stateless unless variable persistence needed

3. **IndexStore Boolean**: Empty `InMemoryIndexStore` is falsy
   - **Fix**: Use `is not None` check
