# 常见问题

开发和使用过程中可能遇到的问题及解决方案。

> 关于关键实现注意事项，详见 [agent-system.md](./agent-system.md#关键实现注意事项)
> 关于调试技巧，详见 [testing.md](./testing.md#调试技巧)

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
