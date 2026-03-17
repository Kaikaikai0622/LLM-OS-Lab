"""
Agent SDK Builder Pattern

通过 Builder 模式快速构建自定义 Agent，只需定义 tools + prompt 即可：

    agent = (
        AgentBuilder()
        .llm(my_llm)
        .sandbox(my_sandbox)
        .system_prompt("You are a data analyst...")
        .index_store(InMemoryIndexStore())
        .max_executions(10)
        .build()
    )
    result = await agent.run("分析这份数据...")
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from agent.index_store import IndexStore, InMemoryIndexStore


class AgentBuilder:
    """Builder pattern for SandboxAgent construction."""

    def __init__(self):
        self._llm: Any = None
        self._sandbox: Any = None
        self._system_prompt: str | None = None
        self._index_store: IndexStore | None = None
        self._workspace_root: str | None = None
        self._max_executions: int = 10
        self._total_timeout: float = 60.0
        self._tool_timeout: float = 15.0
        self._summary_max_chars: int = 2000
        self._verbose: bool = True
        self._has_fetch_tool: bool | None = None

    def llm(self, llm: Any) -> AgentBuilder:
        """设置 LLM（必需）"""
        self._llm = llm
        return self

    def sandbox(self, sandbox: Any) -> AgentBuilder:
        """设置沙箱实例（必需）"""
        self._sandbox = sandbox
        return self

    def system_prompt(self, prompt: str) -> AgentBuilder:
        """自定义 system prompt（可选，不设置则使用默认）"""
        self._system_prompt = prompt
        return self

    def index_store(self, store: IndexStore) -> AgentBuilder:
        """设置索引存储（可选，默认 InMemoryIndexStore）"""
        self._index_store = store
        return self

    def workspace_root(self, path: str) -> AgentBuilder:
        """设置文件工具的工作区根目录（可选）"""
        self._workspace_root = path
        return self

    def max_executions(self, n: int) -> AgentBuilder:
        """最大工具执行次数（默认 10）"""
        self._max_executions = n
        return self

    def total_timeout(self, seconds: float) -> AgentBuilder:
        """总超时时间（秒，默认 60）"""
        self._total_timeout = seconds
        return self

    def tool_timeout(self, seconds: float) -> AgentBuilder:
        """单个工具执行超时（秒，默认 15）"""
        self._tool_timeout = seconds
        return self

    def summary_max_chars(self, n: int) -> AgentBuilder:
        """摘要最大字符数（默认 2000）"""
        self._summary_max_chars = n
        return self

    def verbose(self, enabled: bool = True) -> AgentBuilder:
        """是否打印诊断日志"""
        self._verbose = enabled
        return self

    def has_fetch_tool(self, enabled: bool) -> AgentBuilder:
        """是否暴露 fetch_execution_detail 工具（默认跟随 compress_mode）"""
        self._has_fetch_tool = enabled
        return self

    def build(self) -> "SandboxAgent":
        """
        构建 SandboxAgent 实例

        Raises:
            ValueError: llm 或 sandbox 未设置
        """
        if self._llm is None:
            raise ValueError("llm is required — call .llm(my_llm) before .build()")
        if self._sandbox is None:
            raise ValueError("sandbox is required — call .sandbox(my_sandbox) before .build()")

        from agent.agent import SandboxAgent

        return SandboxAgent(
            llm=self._llm,
            sandbox=self._sandbox,
            index_store=self._index_store,
            workspace_root=self._workspace_root,
            max_executions=self._max_executions,
            total_timeout_seconds=self._total_timeout,
            tool_timeout_seconds=self._tool_timeout,
            summary_max_chars=self._summary_max_chars,
            verbose=self._verbose,
            has_fetch_tool=self._has_fetch_tool,
            custom_system_prompt=self._system_prompt,
        )
