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

## CI/CD 建议

在持续集成中运行：

```bash
#!/bin/bash
set -e

docker-compose run --rm sandbox python tests/smoke_e2e.py
docker-compose run --rm sandbox python test_sandbox.py
```
