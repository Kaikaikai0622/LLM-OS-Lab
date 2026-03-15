"""
历史记录摘要工具

用于将 IndexStore 中的执行历史格式化为 LLM 可理解的上下文，
帮助 Context Mode 下的 LLM 了解之前的执行情况，避免重复错误。
"""

from typing import Optional

from agent.index_store import IndexStore
from agent.tools import _extract_error_info


def build_execution_summary(
    index_store: IndexStore,
    limit: int = 5,
    include_errors: bool = True,
) -> str:
    """
    从 IndexStore 构建执行历史摘要

    Args:
        index_store: 索引存储实例
        limit: 包含最近几条记录
        include_errors: 是否包含错误信息摘要

    Returns:
        格式化的历史摘要字符串，无记录时返回空字符串
    """
    records = index_store.latest(limit)
    if not records:
        return ""

    parts = ["[执行历史摘要]"]

    for i, rec in enumerate(reversed(records), 1):
        status_icon = "✓" if rec.status == "success" else "✗"
        parts.append(
            f"  {i}. [{status_icon}] ID: {rec.execution_id} "
            f"Status: {rec.status}, "
            f"Time: {rec.execution_time:.2f}s"
        )

        # 简要提及输出规模
        stdout_preview = (rec.stdout or "")[:50]
        if len(rec.stdout or "") > 50:
            stdout_preview += "..."
        if stdout_preview:
            parts.append(f"      Output preview: {stdout_preview}")

        # 错误信息摘要（使用结构化提取）
        if include_errors and rec.status == "error" and rec.stderr:
            error_info = _extract_error_info(rec.stderr)
            if error_info["error_type"]:
                error_summary = f"{error_info['error_type']}: {error_info['error_message'] or ''}"
                if error_info["error_line"]:
                    error_summary += f" (at {error_info['error_line']})"
                parts.append(f"      Error: {error_summary}")
            else:
                # 回退：从 stderr 尾部取摘要
                stderr_preview = rec.stderr[-80:]
                if len(rec.stderr) > 80:
                    stderr_preview = "..." + stderr_preview
                parts.append(f"      Error: {stderr_preview}")

    parts.append("[历史摘要结束]")
    return "\n".join(parts)
