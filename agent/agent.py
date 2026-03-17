"""
SandboxAgent 主封装

提供高层次的 Agent 接口，封装工作流细节
"""
import time
from typing import Any, Optional, Callable
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from agent.schemas import AgentState
from agent.index_store import IndexStore, InMemoryIndexStore, NoOpIndexStore
from agent.prompts import PromptBuilder
from agent.workflow import create_simple_workflow
from agent.tools import reset_fetch_execution_detail_call_count


@dataclass
class AgentResult:
    """Agent 执行结果"""
    answer: str
    execution_count: int
    last_execution_id: Optional[str]
    messages: list
    stopped_by_limit: bool = False
    stop_reason: Optional[str] = None  # "max_executions" | "total_timeout" | "no_tool_calls" | None
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_total_tokens: int = 0
    max_prompt_tokens: int = 0
    elapsed_seconds: float = 0.0
    tool_metrics: list[dict] | None = None
    round_token_history: list[dict] | None = None
    # Phase 1: 新增用户体验度量字段
    first_token_latency_ms: float = 0.0  # 首 Token 延迟（毫秒）
    per_round_llm_latency: list[float] | None = None  # 每轮 LLM 调用耗时（秒）
    per_round_tool_latency: list[float] | None = None  # 每轮工具执行耗时（秒）
    compression_ratio: float = 0.0  # 消息压缩前后 Token 比
    fetch_hit_count: int = 0  # fetch_execution_detail 被调用次数
    task_success: bool = False  # 是否正常收敛（stop_reason == "no_tool_calls"）


class SandboxAgent:
    """
    沙箱 Agent 主类

    封装 LLM、沙箱、索引存储，提供简洁的 run() 接口

    使用示例：
        agent = SandboxAgent(
            llm=my_llm,
            sandbox=my_sandbox,
            index_store=InMemoryIndexStore(),
            max_executions=10,
            total_timeout_seconds=60,
        )
        result = await agent.run("计算1到100的和")
        print(result.answer)
    """

    def __init__(
        self,
        llm: Callable,
        sandbox: Any,
        index_store: Optional[IndexStore] = None,
        workspace_root: Optional[str] = None,
        max_executions: int = 10,
        total_timeout_seconds: float = 60.0,
        tool_timeout_seconds: float = 15.0,
        summary_max_chars: int = 2000,
        verbose: bool = True,
        has_fetch_tool: Optional[bool] = None,
        custom_system_prompt: Optional[str] = None,
    ):
        """
        初始化 Agent

        Args:
            llm: LLM 调用函数，接收消息列表返回 AIMessage
            sandbox: 沙箱实例（如 FixedPyodideSandbox）
            index_store: 索引存储实例，默认使用 InMemoryIndexStore
            workspace_root: 文件读写工具可访问的工作区根目录，默认当前目录
            max_executions: 最大工具执行次数
            total_timeout_seconds: 总超时时间（秒），默认 60 秒
            tool_timeout_seconds: 单个工具执行超时（秒），默认 15 秒
            summary_max_chars: 执行结果摘要最大字符数，默认 2000
            verbose: 是否打印诊断日志
            custom_system_prompt: 自定义 system prompt（SDK Builder 用），为 None 时使用默认
        """
        self.llm = llm
        self.sandbox = sandbox
        self.index_store = index_store if index_store is not None else InMemoryIndexStore()
        self.workspace_root = str(Path(workspace_root or ".").resolve())
        self.max_executions = max_executions
        self.total_timeout_seconds = total_timeout_seconds
        self.tool_timeout_seconds = tool_timeout_seconds
        self.summary_max_chars = summary_max_chars
        self.verbose = verbose
        self.custom_system_prompt = custom_system_prompt

        # compress_mode：非 NoOpIndexStore 即启用消息压缩和历史摘要注入
        self.compress_mode = not isinstance(self.index_store, NoOpIndexStore)
        # has_fetch_tool：是否向 LLM 暴露 fetch_execution_detail 工具（CM 专属）
        # has_fetch_tool=None 时自动跟随 compress_mode
        self.has_fetch_tool = has_fetch_tool if has_fetch_tool is not None else self.compress_mode
        # context_mode 供兼容性保留：等同于 has_fetch_tool
        self.context_mode = self.has_fetch_tool

        # 创建工作流（compress_mode 启用消息压缩）
        self.workflow = create_simple_workflow(
            llm=self.llm,
            sandbox=self.sandbox,
            index_store=self.index_store,
            workspace_root=self.workspace_root,
            max_executions=self.max_executions,
            tool_timeout_seconds=self.tool_timeout_seconds,
            summary_max_chars=self.summary_max_chars,
            max_tool_messages_in_context=3,
            compress_old_messages=self.compress_mode,
            verbose=self.verbose,
        )

    async def run(self, query: str) -> AgentResult:
        """
        运行 Agent 处理用户查询

        Args:
            query: 用户输入

        Returns:
            AgentResult: 包含 answer、execution_count、last_execution_id、stop_reason 等
        """
        # Phase 1: 重置 fetch_execution_detail 调用计数器
        reset_fetch_execution_detail_call_count()

        # 构造初始状态
        if self.custom_system_prompt:
            system_prompt = self.custom_system_prompt
        else:
            system_prompt = PromptBuilder.build_system_prompt(context_mode=self.has_fetch_tool)
        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query),
            ],
            "execution_count": 0,
            "max_executions": self.max_executions,
            "last_execution_id": None,
            "final_answer": None,
            "started_at": time.monotonic(),  # 记录开始时间
            "total_timeout_seconds": self.total_timeout_seconds,
            "tool_timeout_seconds": self.tool_timeout_seconds,
            "summary_max_chars": self.summary_max_chars,
            "stop_reason": None,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "llm_total_tokens": 0,
            "max_prompt_tokens": 0,
            "elapsed_seconds": 0.0,
            "tool_metrics": [],
            "round_token_history": [],
            # Phase 1: 初始化用户体验度量字段
            "per_round_llm_latency": [],
            "per_round_tool_latency": [],
            "compression_ratio": 0.0,
            "fetch_hit_count": 0,
            "last_compressed_message_count": 0,
        }

        # 执行工作流
        final_state = await self.workflow(initial_state)

        # 提取结果
        execution_count = final_state.get("execution_count", 0)
        last_execution_id = final_state.get("last_execution_id")
        final_answer = final_state.get("final_answer", "")
        messages = final_state.get("messages", [])
        stop_reason = final_state.get("stop_reason")
        llm_prompt_tokens = final_state.get("llm_prompt_tokens", 0)
        llm_completion_tokens = final_state.get("llm_completion_tokens", 0)
        llm_total_tokens = final_state.get("llm_total_tokens", 0)
        max_prompt_tokens = final_state.get("max_prompt_tokens", 0)
        elapsed_seconds = final_state.get("elapsed_seconds", 0.0)
        tool_metrics = final_state.get("tool_metrics", [])
        round_token_history = final_state.get("round_token_history", [])
        # Phase 1: 提取新增的用户体验度量字段
        per_round_llm_latency = final_state.get("per_round_llm_latency", [])
        per_round_tool_latency = final_state.get("per_round_tool_latency", [])
        compression_ratio = final_state.get("compression_ratio", 0.0)
        fetch_hit_count = final_state.get("fetch_hit_count", 0)

        # 根据 stop_reason 确定 stopped_by_limit
        # total_timeout 和 max_executions 都算作被限制停止
        stopped_by_limit = stop_reason in ("max_executions", "total_timeout")

        # 如果没有 final_answer，尝试从最后一条消息提取
        if not final_answer and messages:
            last_message = messages[-1]
            if isinstance(last_message, dict):
                final_answer = last_message.get("content", "")
            else:
                final_answer = getattr(last_message, "content", "")

        # Phase 1: 计算 task_success（是否正常收敛）
        task_success = stop_reason == "no_tool_calls"

        return AgentResult(
            answer=final_answer or "",
            execution_count=execution_count,
            last_execution_id=last_execution_id,
            messages=messages,
            stopped_by_limit=stopped_by_limit,
            stop_reason=stop_reason,
            llm_prompt_tokens=llm_prompt_tokens,
            llm_completion_tokens=llm_completion_tokens,
            llm_total_tokens=llm_total_tokens,
            max_prompt_tokens=max_prompt_tokens,
            elapsed_seconds=elapsed_seconds,
            tool_metrics=tool_metrics,
            round_token_history=round_token_history,
            # Phase 1: 新增用户体验度量字段
            first_token_latency_ms=0.0,  # 暂时设为 0，后续 streaming 实现后可更新
            per_round_llm_latency=per_round_llm_latency,
            per_round_tool_latency=per_round_tool_latency,
            compression_ratio=compression_ratio,
            fetch_hit_count=fetch_hit_count,
            task_success=task_success,
        )

    def get_execution_record(self, execution_id: str) -> Optional[Any]:
        """
        根据 execution_id 获取完整执行记录

        Args:
            execution_id: 执行ID

        Returns:
            ExecutionRecord | None
        """
        return self.index_store.get(execution_id)
