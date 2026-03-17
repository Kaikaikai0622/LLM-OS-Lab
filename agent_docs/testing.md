# 测试指南

项目包含多层次的测试体系。

## 端到端测试

验证完整链路：LLM API → Agent → 沙箱执行

```bash
docker-compose run --rm sandbox python tests/smoke_e2e.py
```

测试用例：
1. **纯知识问答** - 验证无需工具的场景
2. **代码执行任务** - 验证工具调用、索引存储
3. **错误恢复** - 验证错误处理和记录

## 阶段冒烟测试

按实现阶段划分的测试：

```bash
# 阶段1：索引存储
docker-compose run --rm sandbox python tests/smoke_phase1.py

# 阶段2：工具
docker-compose run --rm sandbox python tests/smoke_phase2.py

# 阶段3：工作流（StateGraph）
docker-compose run --rm sandbox python tests/smoke_phase3.py

# 阶段3 扩展：多 tool_calls 测试
docker-compose run --rm sandbox python tests/smoke_phase3_multi_toolcalls.py

# 阶段3 扩展：总超时测试
docker-compose run --rm sandbox python tests/smoke_phase3_total_timeout.py

# 阶段4：CLI
docker-compose run --rm sandbox python tests/smoke_phase4.py
```

## 沙箱功能测试

```bash
# 综合验证测试（延迟、输出捕获、异常隔离）
docker-compose run --rm sandbox python test_sandbox.py

# 状态模式对比测试
docker-compose run --rm sandbox python test_stateful.py
```

## 测试结构

```
tests/
├── smoke_e2e.py                   # 端到端连通性测试
├── smoke_phase1.py                # 阶段1：索引存储
├── smoke_phase2.py                # 阶段2：工具
├── smoke_phase3.py                # 阶段3：工作流
├── smoke_phase3_multi_toolcalls.py # 多 tool_calls 顺序执行测试
├── smoke_phase3_total_timeout.py   # 总超时控制测试
└── smoke_phase4.py                # 阶段4：CLI
```

### 新增测试说明（StateGraph 迁移后）

**smoke_phase3_multi_toolcalls.py**：验证单轮多 tool_calls 顺序执行
- FakeLLM 单轮返回 2 个 tool_calls
- 断言顺序执行
- 断言 execution_count == 2
- 断言存在 2 条 ToolMessage

**smoke_phase3_total_timeout.py**：验证 total_timeout_seconds 超时机制
- 设置极小超时时间（如 0.05s）
- FakeLLM 持续返回 tool_calls
- 断言 stop_reason == "total_timeout"
- 验证 timeout 优先级高于 max_executions

## 编写新测试

### 基础测试模板

```python
import asyncio
import sys
from pathlib import Path

# 设置项目根目录
PROJECT_ROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, PROJECT_ROOT)

async def test_something():
    """测试描述"""
    from agent import InMemoryIndexStore

    store = InMemoryIndexStore()
    execution_id = store.save({
        "status": "success",
        "stdout": "test output",
    })

    assert execution_id is not None
    assert len(store) == 1
    print("✅ 测试通过")

if __name__ == "__main__":
    asyncio.run(test_something())
```

### 带 LLM 的测试

```python
import os
from dotenv import load_dotenv

# 加载 .env
load_dotenv(Path(PROJECT_ROOT) / ".env")

# 检查 API Key
api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
if not api_key:
    print("[SKIP] API Key 未设置")
    sys.exit(0)
```

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
    base_url="https://dashscope.aliyun.com/compatible-mode/v1",
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

## CI/CD 建议

在持续集成中运行：

```bash
#!/bin/bash
set -e

docker-compose run --rm sandbox python tests/smoke_e2e.py
docker-compose run --rm sandbox python test_sandbox.py
```
