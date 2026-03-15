# 快速开始

Agent 系统的快速入门指南。

## 环境配置

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置 API Key：

```bash
DASHSCOPE_API_KEY=sk-your-api-key
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 运行 Agent

### 使用 Docker（推荐）

```bash
# 基本用法
docker-compose run --rm sandbox python -m agent "计算 1 到 100 的和"

# 指定最大执行轮次
docker-compose run --rm sandbox python -m agent "计算 1 到 100 的和" --max-executions 5

# 静默模式
docker-compose run --rm sandbox python -m agent "计算 1 到 100 的和" --quiet
```

### 本地运行

```bash
pip install -r requirements.txt
python -m agent "计算 1 到 100 的和"
```

## 快速测试

运行端到端测试验证安装：

```bash
docker-compose run --rm sandbox python tests/smoke_e2e.py
```

预期输出：
```
============================================================
端到端连通性测试
============================================================
...
✅ E2E_SMOKE_PASS - 端到端连通性正常
```

## 编程方式使用

```python
import asyncio
from agent import SandboxAgent, InMemoryIndexStore
from sandbox_wrapper import FixedPyodideSandbox
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

class CodeInput(BaseModel):
    code: str = Field(description="Python code to execute")

tool = StructuredTool.from_function(
    func=lambda code: code,
    name="execute_python",
    description="Execute Python code in sandbox",
    args_schema=CodeInput,
)

llm = ChatOpenAI(
    model="qwen-plus",
    api_key="sk-xxx",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0,
).bind_tools([tool])

async def main():
    agent = SandboxAgent(
        llm=llm.invoke,
        sandbox=FixedPyodideSandbox(),
        index_store=InMemoryIndexStore(),
        max_executions=10,
        total_timeout_seconds=60,  # Agent 总超时时间
        verbose=True,
    )
    result = await agent.run("计算斐波那契数列前10项")
    print(result.answer)
    print(f"执行次数: {result.execution_count}")
    print(f"停止原因: {result.stop_reason}")

asyncio.run(main())
```

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `DASHSCOPE_API_KEY` | 是 | - | 阿里云百炼 API Key |
| `LLM_MODEL` | 否 | qwen-plus | 模型名称 |
| `LLM_BASE_URL` | 否 | 阿里云百炼 | API 基础 URL |
| `AGENT_MAX_EXECUTIONS` | 否 | 10 | 最大执行次数 |
| `AGENT_TOTAL_TIMEOUT_SECONDS` | 否 | 60 | Agent 总超时（秒） |
| `AGENT_TOOL_TIMEOUT_SECONDS` | 否 | 15 | 工具超时（秒） |
| `AGENT_SUMMARY_MAX_CHARS` | 否 | 500 | 摘要最大字符数 |
| `AGENT_ALLOW_NET` | 否 | true | 是否允许网络访问 |

## 下一步

- [architecture.md](architecture.md) - 了解系统架构
- [agent-system.md](agent-system.md) - 深入了解 Agent 组件
