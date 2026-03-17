"""
LangGraph StateGraph 工作流定义

实现可循环的 Agent 主流程：
START -> agent_node -> [condition] -> tool_executor -> agent_node
                    -> finalizer -> END
"""
import time
import json
from typing import Any, Callable, Optional
from dataclasses import dataclass
from pathlib import Path

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

from agent.schemas import AgentState, ToolResult
from agent.prompts import PromptBuilder
from agent.tools import (
    execute_python,
    fetch_execution_detail,
    read_workspace_file,
    write_workspace_file,
    ExecutePythonConfig,
    get_fetch_execution_detail_call_count,
)


# 类型定义
LLMCallable = Callable[[list], Any]  # LLM 调用接口


def _normalize_tool_call(tool_call: Any) -> dict:
    """将不同 provider 的 tool_call 格式统一为 LangChain 期望格式。"""
    if not isinstance(tool_call, dict):
        return {
            "id": "unknown",
            "name": "",
            "args": {},
            "type": "tool_call",
        }

    # 已是 LangChain 常用格式
    if "name" in tool_call and "args" in tool_call:
        return {
            "id": tool_call.get("id", "unknown"),
            "name": tool_call.get("name", ""),
            "args": tool_call.get("args", {}) or {},
            "type": "tool_call",
        }

    # OpenAI 风格: {"type":"function", "function": {"name":..., "arguments": ...}}
    function_block = tool_call.get("function", {}) or {}
    name = tool_call.get("name") or function_block.get("name", "")
    raw_arguments = (
        tool_call.get("args")
        if tool_call.get("args") is not None
        else tool_call.get("arguments", function_block.get("arguments", {}))
    )

    if isinstance(raw_arguments, str):
        try:
            args = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except json.JSONDecodeError:
            args = {"code": raw_arguments}
    elif isinstance(raw_arguments, dict):
        args = raw_arguments
    else:
        args = {}

    return {
        "id": tool_call.get("id", "unknown"),
        "name": name,
        "args": args,
        "type": "tool_call",
    }


def _normalize_tool_calls(tool_calls: Any) -> list[dict]:
    """归一化 tool_calls 列表。"""
    if not tool_calls:
        return []
    return [_normalize_tool_call(tc) for tc in tool_calls]


def _normalize_ai_message(response: Any) -> AIMessage:
    """将 LLM 返回值标准化为 AIMessage，避免消息类型不兼容。"""
    if isinstance(response, AIMessage):
        return AIMessage(
            content=response.content or "",
            tool_calls=_normalize_tool_calls(getattr(response, "tool_calls", []) or []),
        )

    if isinstance(response, BaseMessage):
        return AIMessage(
            content=getattr(response, "content", "") or "",
            tool_calls=_normalize_tool_calls(getattr(response, "tool_calls", []) or []),
        )

    if isinstance(response, dict):
        return AIMessage(
            content=response.get("content", "") or "",
            tool_calls=_normalize_tool_calls(response.get("tool_calls", []) or []),
        )

    return AIMessage(
        content=getattr(response, "content", "") or str(response),
        tool_calls=_normalize_tool_calls(getattr(response, "tool_calls", []) or []),
    )


def _extract_token_usage(response: Any) -> tuple[int, int, int]:
    """提取 LLM token 用量，兼容常见 LangChain provider 字段。"""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    usage_meta = getattr(response, "usage_metadata", None) or {}
    if isinstance(usage_meta, dict):
        prompt_tokens = int(usage_meta.get("input_tokens", 0) or usage_meta.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage_meta.get("output_tokens", 0) or usage_meta.get("completion_tokens", 0) or 0)
        total_tokens = int(usage_meta.get("total_tokens", 0) or 0)

    # 兼容 response_metadata.token_usage
    if (prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0):
        response_meta = getattr(response, "response_metadata", None) or {}
        if isinstance(response_meta, dict):
            token_usage = response_meta.get("token_usage", {}) or {}
            if isinstance(token_usage, dict):
                prompt_tokens = int(token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0) or 0)
                completion_tokens = int(token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0) or 0)
                total_tokens = int(token_usage.get("total_tokens", 0) or 0)

    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens

    return prompt_tokens, completion_tokens, total_tokens


@dataclass
class WorkflowConfig:
    """工作流配置"""
    max_executions: int = 10
    max_tool_messages_in_context: int = 3  # 保留的完整 ToolMessage 数量
    compress_old_messages: bool = True      # 是否压缩旧的 ToolMessage
    verbose: bool = True


class AgentWorkflow:
    """
    LangGraph StateGraph Agent 工作流

    节点:
    - agent_node: 调用 LLM，产出 AIMessage
    - tool_executor: 顺序执行全部 tool_calls
    - finalizer: 写入 final_answer 与 stop_reason

    条件边:
    - agent_node -> tool_executor: 有 tool_calls 且未超时未超限
    - agent_node -> finalizer: 无 tool_calls 或超时或超限
    - tool_executor -> agent_node: 继续下一轮
    """

    def __init__(
        self,
        llm: LLMCallable,
        sandbox: Any,
        index_store: Any,
        workspace_root: Optional[str] = None,
        config: Optional[WorkflowConfig] = None,
    ):
        self.llm = llm
        self.sandbox = sandbox
        self.index_store = index_store
        self.workspace_root = str(Path(workspace_root or ".").resolve())
        self.config = config or WorkflowConfig()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建 StateGraph"""
        # 定义状态图
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("agent_node", self._agent_node)
        workflow.add_node("tool_executor", self._tool_executor)
        workflow.add_node("finalizer", self._finalizer)

        # 设置入口
        workflow.set_entry_point("agent_node")

        # 添加条件边: agent_node -> tool_executor 或 finalizer
        workflow.add_conditional_edges(
            "agent_node",
            self._should_continue,
            {
                "continue": "tool_executor",
                "end": "finalizer",
            },
        )

        # tool_executor 完成后返回 agent_node
        workflow.add_edge("tool_executor", "agent_node")

        # finalizer 结束流程
        workflow.add_edge("finalizer", END)

        return workflow.compile()

    def _compress_message_history(self, messages: list, max_tool_messages: int = 3) -> list:
        """
        压缩历史消息：保留最近 N 条 ToolMessage 完整内容，
        更早的 ToolMessage 和对应的 AIMessage 压缩为简短引用。
        仅用于构造 LLM 输入，不修改实际 state。
        """
        import re
        tool_indices = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]

        if len(tool_indices) <= max_tool_messages:
            return messages  # 无需压缩

        # 需要压缩的 ToolMessage 索引集合（保留最近 max_tool_messages 条完整）
        compress_tool_set = set(tool_indices[:-max_tool_messages])

        # 收集被压缩 ToolMessage 的 tool_call_id
        compressed_call_ids = set()
        for i in compress_tool_set:
            compressed_call_ids.add(messages[i].tool_call_id)

        # 找到需要压缩的 AIMessage：当其所有 tool_calls 都被压缩时
        compress_ai_set = set()
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage):
                tc = getattr(msg, "tool_calls", None)
                if tc:
                    ai_call_ids = {c.get("id", "") for c in tc}
                    if ai_call_ids and ai_call_ids.issubset(compressed_call_ids):
                        compress_ai_set.add(i)

        result = []
        for i, msg in enumerate(messages):
            if i in compress_ai_set:
                # 保留 tool_calls 结构（API 要求匹配），压缩 content
                result.append(AIMessage(
                    content="[Previous round reasoning compressed]",
                    tool_calls=msg.tool_calls,
                ))
            elif i in compress_tool_set:
                # 从 ToolMessage content 中提取 execution_id
                exec_id_match = re.search(r'\[execution_id: ([a-f0-9]+)\]', msg.content)
                exec_id = exec_id_match.group(1) if exec_id_match else "unknown"
                result.append(ToolMessage(
                    content=f"[execution_id: {exec_id}] [Compressed] Use fetch_execution_detail to retrieve full output",
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                ))
            else:
                result.append(msg)
        return result

    def _inject_history_summary(self, messages: list) -> list:
        """
        将 IndexStore 中的执行历史摘要注入到 LLM 输入消息中。
        摘要作为 SystemMessage 插入到第一条 SystemMessage 之后。
        仅用于构造 LLM 输入，不修改实际 state。
        """
        from agent.history_utils import build_execution_summary

        summary = build_execution_summary(self.index_store, limit=3, include_errors=True)
        if not summary:
            return messages

        summary_msg = SystemMessage(content=summary)
        result = list(messages)
        for i, msg in enumerate(result):
            if isinstance(msg, SystemMessage):
                result.insert(i + 1, summary_msg)
                return result
        # 未找到 SystemMessage，插入到开头
        result.insert(0, summary_msg)
        return result

    async def _agent_node(self, state: AgentState) -> AgentState:
        """
        LLM 决策节点

        输入 messages，输出 AIMessage（可能含 tool_calls）
        """
        messages = state.get("messages", [])
        execution_count = state.get("execution_count", 0)

        # 构造 LLM 输入消息（可能包含系统提示追加）
        llm_messages = list(messages)

        # 如果达到最大执行次数且还没有最终答案，添加提示
        if execution_count >= self.config.max_executions and not state.get("final_answer"):
            max_exec_message = PromptBuilder.build_max_executions_message(self.config.max_executions)
            llm_messages = llm_messages + [SystemMessage(content=max_exec_message)]

        # 压缩旧 ToolMessage（仅影响 LLM 输入，不影响 state）
        compressed_message_count = 0
        if self.config.compress_old_messages:
            original_llm_messages = llm_messages
            llm_messages = self._compress_message_history(
                llm_messages, self.config.max_tool_messages_in_context
            )
            # 计算被压缩的消息数量
            if len(original_llm_messages) == len(llm_messages):
                compressed_message_count = sum(
                    1 for m in llm_messages
                    if isinstance(m, ToolMessage) and "[Compressed]" in m.content
                )

        # 注入执行历史摘要（Context Mode 且有记录时）
        if self.index_store is not None and len(self.index_store) > 0:
            llm_messages = self._inject_history_summary(llm_messages)

        # Phase 1: 计时 LLM 调用
        llm_start_time = time.perf_counter()

        # 调用 LLM（使用压缩后的输入）
        raw_response = self.llm(llm_messages)

        # Phase 1: 记录 LLM 调用耗时
        llm_latency = time.perf_counter() - llm_start_time
        per_round_llm_latency = list(state.get("per_round_llm_latency") or [])
        per_round_llm_latency.append(round(llm_latency, 4))

        round_prompt_tokens, round_completion_tokens, round_total_tokens = _extract_token_usage(raw_response)
        response = _normalize_ai_message(raw_response)

        llm_prompt_tokens = state.get("llm_prompt_tokens", 0) + round_prompt_tokens
        llm_completion_tokens = state.get("llm_completion_tokens", 0) + round_completion_tokens
        llm_total_tokens = state.get("llm_total_tokens", 0) + round_total_tokens
        max_prompt_tokens = max(state.get("max_prompt_tokens", 0), round_prompt_tokens)

        # 记录 per-round token 数据
        round_token_history = list(state.get("round_token_history") or [])
        round_token_history.append({
            "round": execution_count,
            "prompt_tokens": round_prompt_tokens,
            "completion_tokens": round_completion_tokens,
            "total_tokens": round_total_tokens,
        })

        # 打印诊断日志
        if self.config.verbose:
            tool_calls = getattr(response, "tool_calls", None)
            has_tools = bool(tool_calls and len(tool_calls) > 0)
            print(f"[ROUND {execution_count}] tool_calls={'yes' if has_tools else 'no'}")
            print(
                f"  -> tokens round(prompt={round_prompt_tokens}, completion={round_completion_tokens}, total={round_total_tokens}) "
                f"cum(total={llm_total_tokens})"
            )
            print(f"  -> llm_latency={llm_latency:.3f}s")

        # 返回更新后的状态
        return {
            **state,
            "messages": messages + [response],
            "llm_prompt_tokens": llm_prompt_tokens,
            "llm_completion_tokens": llm_completion_tokens,
            "llm_total_tokens": llm_total_tokens,
            "max_prompt_tokens": max_prompt_tokens,
            "round_token_history": round_token_history,
            "per_round_llm_latency": per_round_llm_latency,
            "last_compressed_message_count": compressed_message_count,
        }

    async def _tool_executor(self, state: AgentState) -> AgentState:
        """
        工具执行节点

        解析 AIMessage.tool_calls，顺序执行全部 tool_calls，
        生成 ToolMessage 回注，更新执行计数
        """
        messages = state.get("messages", [])
        if not messages:
            return state

        # 获取最后一条 AI 消息
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None) or []

        if not tool_calls:
            return state

        # 顺序执行所有 tool_calls
        new_messages = list(messages)  # 复制消息列表
        execution_count = state.get("execution_count", 0)
        last_execution_id: Optional[str] = state.get("last_execution_id")
        tool_metrics = list(state.get("tool_metrics", []))

        # 从 state 读取工具级配置
        tool_timeout_seconds = state.get("tool_timeout_seconds", 15.0)
        summary_max_chars = state.get("summary_max_chars", 2000)

        # 构造 config
        config = ExecutePythonConfig(
            default_timeout=tool_timeout_seconds,
            summary_max_chars=summary_max_chars,
        )

        # Phase 1: 工具执行计时
        tool_start_time = time.perf_counter()

        for tool_call in tool_calls:
            # 解析 tool_call
            function_name = tool_call.get("name", "")
            if not function_name:
                function_name = tool_call.get("function", {}).get("name", "")

            # 获取参数（可能是 "args" 或 "arguments"）
            arguments = tool_call.get("args", tool_call.get("arguments", {}))
            if not arguments:
                arguments = tool_call.get("function", {}).get("arguments", {})

            # 解析参数
            if isinstance(arguments, str):
                import json
                try:
                    args = json.loads(arguments)
                except json.JSONDecodeError:
                    args = {"code": arguments}
            else:
                args = arguments

            code = args.get("code", "") if isinstance(args, dict) else ""

            # 执行工具（支持 execute_python / read_file / write_file）
            if function_name == "execute_python":
                tool_result = await execute_python(
                    code=code,
                    sandbox=self.sandbox,
                    index_store=self.index_store,
                    timeout_seconds=tool_timeout_seconds,
                    config=config,
                )
            elif function_name == "read_file":
                req_path = args.get("path", "") if isinstance(args, dict) else ""
                max_chars = args.get("max_chars", 12000) if isinstance(args, dict) else 12000
                try:
                    max_chars = int(max_chars)
                except (TypeError, ValueError):
                    max_chars = 12000

                tool_result = read_workspace_file(
                    path=req_path,
                    workspace_root=self.workspace_root,
                    max_chars=max_chars,
                )
            elif function_name == "write_file":
                req_path = args.get("path", "") if isinstance(args, dict) else ""
                req_content = args.get("content", "") if isinstance(args, dict) else ""

                tool_result = write_workspace_file(
                    path=req_path,
                    content=req_content,
                    workspace_root=self.workspace_root,
                )
            elif function_name == "fetch_execution_detail":
                req_execution_id = args.get("execution_id") if isinstance(args, dict) else None
                detail_max_chars = args.get("max_chars", 4000) if isinstance(args, dict) else 4000
                try:
                    detail_max_chars = int(detail_max_chars)
                except (TypeError, ValueError):
                    detail_max_chars = 4000

                tool_result = fetch_execution_detail(
                    index_store=self.index_store,
                    execution_id=req_execution_id,
                    fallback_execution_id=last_execution_id,
                    max_chars=detail_max_chars,
                )
            else:
                tool_result = ToolResult(
                    execution_id="N/A",
                    status="error",
                    summary=f"Unknown tool: {function_name}",
                    stdout_chars=0,
                    stderr_chars=0,
                )

            # 打印诊断日志
            if self.config.verbose:
                print(f"  -> execution_id={tool_result.execution_id}, status={tool_result.status}")
                print(
                    "  -> tool_metrics "
                    f"summary_chars={len(tool_result.summary)} stdout_chars={tool_result.stdout_chars} stderr_chars={tool_result.stderr_chars}"
                )

            tool_metrics.append({
                "round": execution_count,
                "tool_name": function_name,
                "execution_id": tool_result.execution_id,
                "status": tool_result.status,
                "summary_chars": len(tool_result.summary),
                "stdout_chars": tool_result.stdout_chars,
                "stderr_chars": tool_result.stderr_chars,
            })

            # 构造 ToolMessage（注入 execution_id 供后续压缩和 LLM 引用）
            content_with_id = f"[execution_id: {tool_result.execution_id}]\n{tool_result.summary}"
            tool_message = ToolMessage(
                content=content_with_id,
                tool_call_id=tool_call.get("id", "unknown"),
                name=function_name,
            )

            # 追加到消息列表
            new_messages.append(tool_message)
            execution_count += 1
            last_execution_id = tool_result.execution_id

        # Phase 1: 计算本轮工具执行总耗时
        tool_latency = time.perf_counter() - tool_start_time
        per_round_tool_latency = list(state.get("per_round_tool_latency") or [])
        per_round_tool_latency.append(round(tool_latency, 4))

        # Phase 1: 计算压缩比（压缩后消息长度 / 原始消息长度）
        compression_ratio = state.get("compression_ratio", 0.0)
        last_compressed_count = state.get("last_compressed_message_count", 0)
        if last_compressed_count > 0 and len(messages) > 0:
            # 压缩比 = 被压缩的消息数 / 总消息数
            compression_ratio = round(last_compressed_count / len(messages), 4)

        return {
            **state,
            "messages": new_messages,
            "execution_count": execution_count,
            "last_execution_id": last_execution_id,
            "tool_metrics": tool_metrics,
            "per_round_tool_latency": per_round_tool_latency,
            "compression_ratio": compression_ratio,
        }

    def _check_timeout(self, state: AgentState) -> bool:
        """
        检查是否达到总超时时间

        Returns:
            True 如果已超时，False 否则
        """
        started_at = state.get("started_at")
        total_timeout = state.get("total_timeout_seconds")

        if started_at is None or total_timeout is None:
            return False

        elapsed = time.monotonic() - started_at
        return elapsed >= total_timeout

    def _should_continue(self, state: AgentState) -> str:
        """
        条件边判断：决定流程走向

        优先级：total_timeout > max_executions > tool_calls > no_tool_calls

        Returns:
            "continue": 继续到 tool_executor
            "end": 结束到 finalizer
        """
        messages = state.get("messages", [])
        execution_count = state.get("execution_count", 0)

        # 检查超时（最高优先级）
        if self._check_timeout(state):
            if self.config.verbose:
                print(f"[STOP] total_timeout reached")
            return "end"

        # 检查是否达到最大执行次数
        if execution_count >= self.config.max_executions:
            if self.config.verbose:
                print(f"[STOP] max_executions ({self.config.max_executions}) reached")
            return "end"

        # 检查最后一条消息是否有 tool_calls
        if not messages:
            return "end"

        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None) or []

        if tool_calls:
            return "continue"

        # 没有 tool_calls，流程结束
        return "end"

    async def _finalizer(self, state: AgentState) -> AgentState:
        """
        最终节点

        确定 stop_reason，提取 final_answer
        """
        messages = state.get("messages", [])
        execution_count = state.get("execution_count", 0)

        # 确定 stop_reason（按优先级）
        stop_reason: Optional[str] = None

        # 优先级 1: 总超时
        if self._check_timeout(state):
            stop_reason = "total_timeout"
        # 优先级 2: 达到最大执行次数
        elif execution_count >= self.config.max_executions:
            stop_reason = "max_executions"
        # 优先级 3: 没有 tool_calls（正常结束）
        elif messages:
            last_message = messages[-1]
            tool_calls = getattr(last_message, "tool_calls", None) or []
            if not tool_calls:
                stop_reason = "no_tool_calls"

        # 提取最终答案
        final_answer = ""
        if messages:
            last_message = messages[-1]
            content = getattr(last_message, "content", "")
            if content:
                final_answer = content

        if self.config.verbose:
            started_at = state.get("started_at")
            elapsed_seconds = (time.monotonic() - started_at) if started_at is not None else 0.0
            print(f"[END] execution_count={execution_count}, stop_reason={stop_reason}, elapsed_seconds={elapsed_seconds:.3f}")

        started_at = state.get("started_at")
        elapsed_seconds = (time.monotonic() - started_at) if started_at is not None else 0.0

        # Phase 1: 获取 fetch_execution_detail 调用计数
        fetch_hit_count = get_fetch_execution_detail_call_count()

        return {
            **state,
            "final_answer": final_answer,
            "stop_reason": stop_reason,
            "elapsed_seconds": elapsed_seconds,
            "fetch_hit_count": fetch_hit_count,
        }

    async def invoke(self, state: AgentState) -> AgentState:
        """执行工作流"""
        max_exec = int(state.get("max_executions", self.config.max_executions) or self.config.max_executions)
        recursion_limit = max(50, max_exec * 4)
        return await self.graph.ainvoke(state, config={"recursion_limit": recursion_limit})


def create_workflow(
    llm: LLMCallable,
    sandbox: Any,
    index_store: Any,
    workspace_root: Optional[str] = None,
    config: Optional[WorkflowConfig] = None,
) -> Callable[[AgentState], Any]:
    """
    创建 LangGraph StateGraph 工作流

    Args:
        llm: LLM 调用函数，接收 messages 列表，返回 AIMessage
        sandbox: 沙箱实例
        index_store: 索引存储实例
        config: 工作流配置

    Returns:
        可执行的图函数，接收 AgentState 返回 AgentState
    """
    workflow = AgentWorkflow(llm, sandbox, index_store, workspace_root=workspace_root, config=config)
    return workflow.invoke


def create_simple_workflow(
    llm: LLMCallable,
    sandbox: Any,
    index_store: Any,
    workspace_root: Optional[str] = None,
    max_executions: int = 10,
    tool_timeout_seconds: float = 15.0,
    summary_max_chars: int = 2000,
    max_tool_messages_in_context: int = 3,
    compress_old_messages: bool = True,
    verbose: bool = True,
) -> Callable[[AgentState], Any]:
    """
    简化版工作流创建函数

    与 create_workflow 相同，但参数更简单
    """
    config = WorkflowConfig(
        max_executions=max_executions,
        max_tool_messages_in_context=max_tool_messages_in_context,
        compress_old_messages=compress_old_messages,
        verbose=verbose,
    )
    return create_workflow(llm, sandbox, index_store, workspace_root=workspace_root, config=config)
