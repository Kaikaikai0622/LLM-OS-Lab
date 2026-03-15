"""
最小Agent实现

基于LangGraph + Pyodide沙箱的代码执行Agent

核心功能：
- 通过LLM决策调用代码执行工具
- 执行结果写入索引，仅返回压缩摘要给LLM
- 支持多轮迭代直到任务完成
"""

from agent.schemas import ExecutionRecord, ToolResult, AgentState
from agent.index_store import IndexStore, InMemoryIndexStore, NoOpIndexStore
from agent.tools import (
    execute_python,
    fetch_execution_detail,
    read_workspace_file,
    write_workspace_file,
    run_python_code,
    ExecutePythonConfig,
)
from agent.workflow import create_workflow, create_simple_workflow
from agent.history_utils import build_execution_summary
from agent.agent import SandboxAgent, AgentResult

__all__ = [
    # 数据结构
    "ExecutionRecord",
    "ToolResult",
    "AgentState",
    # 索引存储
    "IndexStore",
    "InMemoryIndexStore",
    "NoOpIndexStore",
    # 工具函数
    "execute_python",
    "fetch_execution_detail",
    "read_workspace_file",
    "write_workspace_file",
    "run_python_code",
    "ExecutePythonConfig",
    # 工作流
    "create_workflow",
    "create_simple_workflow",
    # 历史摘要
    "build_execution_summary",
    # Agent
    "SandboxAgent",
    "AgentResult",
]

__version__ = "0.1.0"
