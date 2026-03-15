# 沙箱系统

基于 Pyodide (WebAssembly) 的 Python 代码沙箱。

## 基础用法

### 使用 PyodideSandbox

```python
from langchain_sandbox import PyodideSandbox

sandbox = PyodideSandbox(allow_net=True)
result = await sandbox.execute("print('hello world')")
print(result.stdout)
```

### 使用 FixedPyodideSandbox（推荐）

修复了 stdout 换行丢失的问题：

```python
from sandbox_wrapper import FixedPyodideSandbox

sandbox = FixedPyodideSandbox(allow_net=True)
result = await sandbox.execute("print('line1')\nprint('line2')")
print(result.stdout)  # 正确显示: 'line1\nline2'
```

## 沙箱行为

- **首次启动**：需要 ~8s 初始化 Pyodide
- **后续执行**：~1.5-2s
- **执行环境**：WebAssembly 隔离环境
- **可用模块**：标准库模块可用，但部分 C 扩展不可用

## 状态模式

### 无状态模式（默认）

每次执行都是独立的：

```python
result1 = await sandbox.execute("x = 100")
result2 = await sandbox.execute("print(x)")  # 错误：x 未定义
```

### 有状态模式

变量在多次执行间保持：

```python
# 需要额外配置实现
```

性能对比：
- 无状态模式：~1.5s
- 有状态模式：~3.3s（由于实例重建开销）

## 已知问题

### stdout 换行丢失

**问题**：`@langchain/pyodide-sandbox` 包使用 `join('')` 而非 `join('\n')` 收集输出

**位置**：JSR 包 `main.ts` 约 325 行

**解决**：使用 `FixedPyodideSandbox` 包装器

```python
from sandbox_wrapper import FixedPyodideSandbox

sandbox = FixedPyodideSandbox(allow_net=True)
```

包装器使用启发式规则恢复换行：
- 检测数字→字母边界（如 "1line" → "1\nline"）
- 检测驼峰命名（如 "fooBar" → "foo\nBar"）
- 特殊关键字检测（"Traceback", "In[" 等）
- 循环打印检测

## 安全限制

- 网络访问：`allow_net` 参数控制
- 内存限制：可设置 `memory_limit_mb`
- 超时控制：可设置 `timeout_seconds`

## Agent 总超时 vs 沙箱超时

需要注意 Agent 级别的超时与沙箱级别的超时的区别：

```python
# Agent 总超时：整个 Agent 运行的时间限制（2026-03-14 新增）
agent = SandboxAgent(
    llm=llm,
    sandbox=sandbox,
    total_timeout_seconds=60,  # 整个 Agent 最多运行 60 秒
)

# 沙箱超时：单次代码执行的时间限制
result = await sandbox.execute(code, timeout_seconds=15)  # 单次执行最多 15 秒
```

- **Agent 总超时**（`total_timeout_seconds`）：控制整个多轮对话的总时间
- **沙箱超时**（`timeout_seconds`）：控制单次 Python 代码执行的时间

Agent 总超时优先级高于 `max_executions`，当两者同时触发时，`stop_reason` 为 `"total_timeout"`。
