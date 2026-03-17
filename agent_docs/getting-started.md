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

所有环境变量均可通过 CLI 参数覆盖（例如 `--model`, `--base-url`, `--api-key`）。

优先级：CLI 参数 > 环境变量 > 默认值

## 使用 AgentBuilder SDK

Builder 模式提供更简洁的自定义 Agent 构建方式：

```python
import asyncio
from agent import AgentBuilder, InMemoryIndexStore
from sandbox_wrapper import FixedPyodideSandbox
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="qwen-plus",
    api_key="sk-xxx",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0,
)

agent = (
    AgentBuilder()
    .llm(llm.invoke)
    .sandbox(FixedPyodideSandbox())
    .system_prompt("You are a data analyst. Focus on statistical analysis.")
    .index_store(InMemoryIndexStore())
    .max_executions(10)
    .total_timeout(60)
    .build()
)

async def main():
    result = await agent.run("分析这组数据的分布特征")
    print(result.answer)

asyncio.run(main())
```

## Docker 开发环境

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

### Local Development

```bash
pip install -r requirements.txt
python -m agent "2+2等于多少"
```

## 更多命令

详见 [cli-reference.md](./cli-reference.md) 获取完整命令参考。

## 下一步

- [architecture.md](architecture.md) - 了解系统架构
- [agent-system.md](agent-system.md) - 深入了解 Agent 组件
