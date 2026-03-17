"""
Agent 核心数据结构定义
用于解耦类型，避免循环引用
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TypedDict, Annotated

from langgraph.graph.message import add_messages


# LangGraph 消息类型导入（延迟导入避免循环依赖）
# 实际使用时从 langchain_core.messages 导入


class AgentState(TypedDict):
    """
    LangGraph Agent 状态定义

    包含工作流中传递的所有状态字段
    """
    messages: Annotated[list, add_messages]  # 对话历史，使用 add_messages 合并
    execution_count: int  # 当前工具执行次数（按实际工具调用次数累计）
    max_executions: int  # 最大执行次数限制
    last_execution_id: Optional[str]  # 最近一次工具执行 ID
    final_answer: Optional[str]  # 最终回答（结束时填充）
    started_at: Optional[float]  # Agent 启动时间（time.monotonic() 时间戳）
    total_timeout_seconds: Optional[float]  # 总超时时间（秒），None 表示无限制
    tool_timeout_seconds: Optional[float]  # 单个工具执行超时（秒），默认 15
    summary_max_chars: Optional[int]  # 执行结果摘要最大字符数，默认 500
    stop_reason: Optional[str]  # 停止原因: "max_executions" | "total_timeout" | "no_tool_calls" | None
    llm_prompt_tokens: Optional[int]  # LLM 输入 token 累计
    llm_completion_tokens: Optional[int]  # LLM 输出 token 累计
    llm_total_tokens: Optional[int]  # LLM 总 token 累计
    max_prompt_tokens: Optional[int]  # 单轮 prompt token 最大值
    elapsed_seconds: Optional[float]  # Agent 运行总耗时（秒）
    tool_metrics: Optional[list[dict]]  # 每次工具调用的观测指标
    round_token_history: Optional[list[dict]]  # 每轮 LLM 调用的 token 记录
    # Phase 1: 新增用户体验度量字段
    per_round_llm_latency: Optional[list[float]]  # 每轮 LLM 调用耗时（秒）
    per_round_tool_latency: Optional[list[float]]  # 每轮工具执行耗时（秒）
    compression_ratio: Optional[float]  # 消息压缩前后 Token 比
    fetch_hit_count: Optional[int]  # fetch_execution_detail 被调用次数
    last_compressed_message_count: Optional[int]  # 上次压缩的消息数量（用于计算压缩比）


@dataclass
class ExecutionRecord:
    """
    代码执行记录

    存储原始执行结果，用于索引和后续检索
    """
    execution_id: str
    status: str  # "success" | "error" | "timeout"
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    execution_time: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "result": self.result,
            "execution_time": self.execution_time,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionRecord":
        """从字典创建实例"""
        return cls(
            execution_id=data["execution_id"],
            status=data["status"],
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            result=data.get("result"),
            execution_time=data.get("execution_time", 0.0),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )


@dataclass
class ToolResult:
    """
    工具执行结果

    返回给LLM的压缩摘要，而非完整原始输出
    """
    execution_id: str
    status: str  # "success" | "error" | "timeout"
    summary: str  # 压缩后的摘要
    stdout_chars: int  # 原始stdout长度（便于追溯）
    stderr_chars: int  # 原始stderr长度

    def to_message(self) -> str:
        """
        转换为LLM可读的摘要消息

        格式示例：
        [Tool Execution Summary]
        - ID: abc123
        - Status: success
        - Output: 5050 (truncated from 10 chars)
        - Summary: 计算结果：1到100的和为5050
        """
        return (
            f"[Tool Execution Summary]\n"
            f"- ID: {self.execution_id}\n"
            f"- Status: {self.status}\n"
            f"- stdout: {self.stdout_chars} chars\n"
            f"- stderr: {self.stderr_chars} chars\n"
            f"- Summary: {self.summary}"
        )
