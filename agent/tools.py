"""
Agent 工具层

提供 Agent 工具：
- execute_python: 沙箱代码执行（执行 -> 索引 -> 摘要）
- fetch_execution_detail: 按 execution_id 查询详细执行记录
"""
import re
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from pathlib import Path

from agent.schemas import ToolResult
from agent.index_store import IndexStore, InMemoryIndexStore

# Phase 1: fetch_execution_detail 调用计数器（用于评估上下文压缩效果）
_fetch_execution_detail_call_count: int = 0


def get_fetch_execution_detail_call_count() -> int:
    """获取 fetch_execution_detail 被调用次数"""
    global _fetch_execution_detail_call_count
    return _fetch_execution_detail_call_count


def reset_fetch_execution_detail_call_count() -> None:
    """重置 fetch_execution_detail 调用计数器"""
    global _fetch_execution_detail_call_count
    _fetch_execution_detail_call_count = 0


def increment_fetch_execution_detail_call_count() -> None:
    """增加 fetch_execution_detail 调用计数器"""
    global _fetch_execution_detail_call_count
    _fetch_execution_detail_call_count += 1


class SandboxProtocol(Protocol):
    """沙箱接口协议，用于依赖注入"""

    async def execute(
        self,
        code: str,
        timeout_seconds: Optional[float] = None,
        memory_limit_mb: Optional[int] = None,
    ) -> Any:
        """执行代码并返回结果"""
        ...


@dataclass
class ExecutePythonConfig:
    """execute_python 工具配置"""

    default_timeout: float = 15.0
    summary_max_chars: int = 2000
    stderr_max_chars: int = 200


async def execute_python(
    code: str,
    *,
    sandbox: SandboxProtocol,
    index_store: IndexStore,
    timeout_seconds: Optional[float] = None,
    memory_limit_mb: Optional[int] = None,
    config: Optional[ExecutePythonConfig] = None,
) -> ToolResult:
    """
    在沙箱中执行 Python 代码

    流程：
    1. 调用沙箱执行代码
    2. 将原始结果写入索引
    3. 生成压缩摘要
    4. 返回 ToolResult（仅包含摘要，不含完整输出）

    Args:
        code: Python 代码字符串
        sandbox: 沙箱实例（如 FixedPyodideSandbox）
        index_store: 索引存储实例
        timeout_seconds: 超时时间（秒），默认 15s
        memory_limit_mb: 内存限制（MB）
        config: 工具配置

    Returns:
        ToolResult: 包含 execution_id、status、摘要等信息

    异常处理：
        所有沙箱异常都会被捕获并转为 status="error" 的 ToolResult，
        不会向上抛出异常，确保 LangGraph 工作流不被打断。
    """
    cfg = config or ExecutePythonConfig()

    # 防御：空代码检查
    if not code or not code.strip():
        error_result = _create_error_result(
            index_store=index_store,
            error_message="Error: Empty code provided",
            config=cfg,
        )
        return error_result

    # 防御：非法超时值回退
    if timeout_seconds is None or timeout_seconds <= 0:
        timeout_seconds = cfg.default_timeout

    try:
        # 1. 执行代码
        raw_result = await sandbox.execute(
            code=code,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
        )

        # 2. 标准化原始结果为字典
        execution_dict = _normalize_result(raw_result, code)

        # 3. 写入索引
        execution_id = index_store.save(execution_dict)

        # 4. 生成压缩摘要
        summary = _compress_result(
            execution_dict,
            max_chars=cfg.summary_max_chars,
            stderr_max_chars=cfg.stderr_max_chars,
        )

        # 5. 构造 ToolResult
        return ToolResult(
            execution_id=execution_id,
            status=execution_dict["status"],
            summary=summary,
            stdout_chars=len(execution_dict.get("stdout", "")),
            stderr_chars=len(execution_dict.get("stderr", "")),
        )

    except Exception as e:
        # 捕获所有异常，转为结构化错误结果
        error_result = _create_error_result_from_exception(
            index_store=index_store,
            exception=e,
            code=code,
            config=cfg,
        )
        return error_result


def _extract_error_info(stderr: str) -> dict:
    """
    从 stderr 中提取结构化错误信息。

    Python traceback 的有用信息在末尾，提取：
    - error_type: 异常类名 (e.g. ModuleNotFoundError)
    - error_message: 异常消息 (e.g. No module named 'numpy')
    - error_line: 用户代码中出错的行号 (e.g. line 5)
    """
    info: dict[str, Optional[str]] = {
        "error_type": None,
        "error_message": None,
        "error_line": None,
    }
    if not stderr:
        return info

    lines = stderr.strip().splitlines()

    # 从最后一行提取 ErrorType: message
    for line in reversed(lines):
        m = re.match(r"^(\w+(?:Error|Exception|Warning)):\s*(.*)", line)
        if m:
            info["error_type"] = m.group(1)
            info["error_message"] = m.group(2)
            break
        # 有些错误没有消息，如 `KeyboardInterrupt`
        m2 = re.match(r"^(\w+(?:Error|Exception|Warning))$", line)
        if m2:
            info["error_type"] = m2.group(1)
            info["error_message"] = ""
            break

    # 提取用户代码行号: File "<exec>", line N
    for line in reversed(lines):
        m = re.search(r'File "<exec>", line (\d+)', line)
        if m:
            info["error_line"] = f"line {m.group(1)}"
            break

    return info


def _normalize_result(raw_result: Any, code: str) -> dict:
    """
    将沙箱返回对象标准化为可存储字典

    支持多种沙箱返回格式（FixedExecutionResult, CodeExecutionResult 等）
    """
    # 尝试从常见属性中提取字段
    status = getattr(raw_result, "status", "unknown")
    stdout = getattr(raw_result, "stdout", "") or ""
    stderr = getattr(raw_result, "stderr", "") or ""
    result = getattr(raw_result, "result", None)
    execution_time = getattr(raw_result, "execution_time", 0.0)

    # 如果是字典格式
    if isinstance(raw_result, dict):
        status = raw_result.get("status", "unknown")
        stdout = raw_result.get("stdout", "") or ""
        stderr = raw_result.get("stderr", "") or ""
        result = raw_result.get("result")
        execution_time = raw_result.get("execution_time", 0.0)

    d = {
        "status": status,
        "stdout": stdout,
        "stderr": stderr,
        "result": result,
        "execution_time": execution_time,
        "code": code,
    }

    # 从 stderr 提取结构化错误信息
    if status == "error" and stderr:
        error_info = _extract_error_info(stderr)
        if error_info["error_type"]:
            d["error_type"] = error_info["error_type"]
        if error_info["error_message"] is not None:
            d["error_message"] = error_info["error_message"]
        if error_info["error_line"]:
            d["error_line"] = error_info["error_line"]

    return d


def _compress_result(
    execution_dict: dict,
    max_chars: int,
    stderr_max_chars: int,
) -> str:
    """
    压缩执行结果为摘要

    策略：
    - stdout 截断到 max_chars，超出部分标记 ...truncated
    - stderr 单独截断，避免错误信息淹没主输出
    - 错误时增加结构化字段：error_type、error_message_preview
    - 包含 status 和 output 长度信息
    """
    status = execution_dict.get("status", "unknown")
    stdout = execution_dict.get("stdout", "")
    stderr = execution_dict.get("stderr", "")
    result = execution_dict.get("result")
    error_type = execution_dict.get("error_type")

    # 截断 stdout
    if len(stdout) > max_chars:
        stdout_preview = stdout[:max_chars] + "\n...[truncated]"
    else:
        stdout_preview = stdout

    # 构建摘要
    parts = [f"Status: {status}"]

    # 错误状态时添加结构化错误信息（帮助 LLM 无需 fetch 即可诊断）
    if status == "error":
        error_message = execution_dict.get("error_message")
        error_line = execution_dict.get("error_line")
        if error_type:
            parts.append(f"Error Type: {error_type}")
        if error_message is not None:
            parts.append(f"Error Message: {error_message}")
        if error_line:
            parts.append(f"Error Location: {error_line}")

    if stdout_preview:
        parts.append(f"Output:\n{stdout_preview}")

    # 如果有 stderr，从尾部截断（Python traceback 有用信息在末尾）
    if stderr:
        if len(stderr) > stderr_max_chars:
            stderr_preview = "...[truncated]" + stderr[-stderr_max_chars:]
        else:
            stderr_preview = stderr
        parts.append(f"Errors:\n{stderr_preview}")

    # 如果有 result，简要提及
    if result is not None:
        result_str = str(result)
        if len(result_str) > 100:
            result_str = result_str[:100] + "...[truncated]"
        parts.append(f"Return value: {result_str}")

    return "\n\n".join(parts)


def _create_error_result(
    index_store: IndexStore,
    error_message: str,
    config: ExecutePythonConfig,
) -> ToolResult:
    """创建错误类型的 ToolResult（非异常场景）"""
    execution_dict = {
        "status": "error",
        "stdout": "",
        "stderr": error_message,
        "result": None,
        "execution_time": 0.0,
        "error_type": "ValidationError",
    }

    execution_id = index_store.save(execution_dict)

    summary = _compress_result(
        execution_dict,
        max_chars=config.summary_max_chars,
        stderr_max_chars=config.stderr_max_chars,
    )

    return ToolResult(
        execution_id=execution_id,
        status="error",
        summary=summary,
        stdout_chars=0,
        stderr_chars=len(error_message),
    )


def fetch_execution_detail(
    *,
    index_store: IndexStore,
    execution_id: Optional[str] = None,
    fallback_execution_id: Optional[str] = None,
    max_chars: int = 4000,
) -> ToolResult:
    """
    查询完整执行记录详情（供 Agent 按需调用）
    """
    # Phase 1: 增加调用计数器
    increment_fetch_execution_detail_call_count()
    """
    查询完整执行记录详情（供 Agent 按需调用）

    Args:
        index_store: 索引存储实例
        execution_id: 要查询的 execution_id（优先）
        fallback_execution_id: execution_id 缺失时使用的兜底 ID（通常为 last_execution_id）
        max_chars: 详情最大字符数，防止上下文爆炸

    Returns:
        ToolResult: 详情查询结果（summary 字段承载详细内容）
    """
    resolved_id = (execution_id or fallback_execution_id or "").strip()

    if not resolved_id:
        summary = (
            "Detail lookup failed: missing execution_id. "
            "Provide an execution_id or first run execute_python."
        )
        return ToolResult(
            execution_id="N/A",
            status="error",
            summary=summary,
            stdout_chars=0,
            stderr_chars=len(summary),
        )

    record = index_store.get(resolved_id)
    if record is None:
        summary = (
            f"Detail lookup failed: execution_id={resolved_id} not found. "
            "This can happen in no-index mode or when the id is invalid."
        )
        return ToolResult(
            execution_id=resolved_id,
            status="error",
            summary=summary,
            stdout_chars=0,
            stderr_chars=len(summary),
        )

    detail = (
        f"[Execution Detail]\n"
        f"- execution_id: {record.execution_id}\n"
        f"- status: {record.status}\n"
        f"- execution_time: {record.execution_time}\n"
        f"- created_at: {record.created_at}\n\n"
        f"[STDOUT]\n{record.stdout or '<empty>'}\n\n"
        f"[STDERR]\n{record.stderr or '<empty>'}\n\n"
        f"[RESULT]\n{record.result if record.result is not None else '<none>'}"
    )

    if max_chars > 0 and len(detail) > max_chars:
        detail = detail[:max_chars] + "\n...[truncated]"

    return ToolResult(
        execution_id=record.execution_id,
        status="success",
        summary=detail,
        stdout_chars=len(record.stdout or ""),
        stderr_chars=len(record.stderr or ""),
    )


def _resolve_workspace_path(path: str, workspace_root: str) -> tuple[Optional[Path], Optional[str]]:
    """解析并校验路径，确保访问范围在 workspace_root 内。"""
    if not path or not path.strip():
        return None, "Path is empty"

    root = Path(workspace_root).resolve()
    target = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()

    try:
        target.relative_to(root)
    except ValueError:
        return None, f"Path '{path}' is outside workspace root"

    return target, None


def read_workspace_file(
    *,
    path: str,
    workspace_root: str,
    max_chars: int = 12000,
) -> ToolResult:
    """读取 workspace 内文件内容（与索引模式无关）。"""
    target, error = _resolve_workspace_path(path, workspace_root)
    if error:
        return ToolResult(
            execution_id="N/A",
            status="error",
            summary=f"Read file failed: {error}",
            stdout_chars=0,
            stderr_chars=len(error),
        )

    if target is None or not target.exists() or not target.is_file():
        msg = f"File not found: {path}"
        return ToolResult(
            execution_id="N/A",
            status="error",
            summary=f"Read file failed: {msg}",
            stdout_chars=0,
            stderr_chars=len(msg),
        )

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        err = f"Cannot read file '{path}': {type(e).__name__}: {e}"
        return ToolResult(
            execution_id="N/A",
            status="error",
            summary=f"Read file failed: {err}",
            stdout_chars=0,
            stderr_chars=len(err),
        )

    full_chars = len(content)
    if max_chars > 0 and full_chars > max_chars:
        preview = content[:max_chars] + "\n...[truncated]"
    else:
        preview = content

    summary = f"[File Read]\npath: {path}\nchars: {full_chars}\n\n{preview}"
    return ToolResult(
        execution_id="N/A",
        status="success",
        summary=summary,
        stdout_chars=full_chars,
        stderr_chars=0,
    )


def write_workspace_file(
    *,
    path: str,
    content: str,
    workspace_root: str,
) -> ToolResult:
    """写入 workspace 内文件内容（覆盖写入，与索引模式无关）。"""
    target, error = _resolve_workspace_path(path, workspace_root)
    if error:
        return ToolResult(
            execution_id="N/A",
            status="error",
            summary=f"Write file failed: {error}",
            stdout_chars=0,
            stderr_chars=len(error),
        )

    try:
        assert target is not None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
    except Exception as e:
        err = f"Cannot write file '{path}': {type(e).__name__}: {e}"
        return ToolResult(
            execution_id="N/A",
            status="error",
            summary=f"Write file failed: {err}",
            stdout_chars=0,
            stderr_chars=len(err),
        )

    written_chars = len(content or "")
    summary = f"[File Write]\npath: {path}\nwritten_chars: {written_chars}"
    return ToolResult(
        execution_id="N/A",
        status="success",
        summary=summary,
        stdout_chars=written_chars,
        stderr_chars=0,
    )


def _create_error_result_from_exception(
    index_store: IndexStore,
    exception: Exception,
    code: str,
    config: ExecutePythonConfig,
) -> ToolResult:
    """从异常创建错误类型的 ToolResult"""
    error_type = type(exception).__name__
    error_message = f"Exception: {error_type}: {str(exception)}"

    execution_dict = {
        "status": "error",
        "stdout": "",
        "stderr": error_message,
        "result": None,
        "execution_time": 0.0,
        "code": code,
        "error_type": error_type,
    }

    execution_id = index_store.save(execution_dict)

    summary = _compress_result(
        execution_dict,
        max_chars=config.summary_max_chars,
        stderr_max_chars=config.stderr_max_chars,
    )

    return ToolResult(
        execution_id=execution_id,
        status="error",
        summary=summary,
        stdout_chars=0,
        stderr_chars=len(error_message),
    )


# 便捷函数：使用默认配置快速执行
async def run_python_code(
    code: str,
    *,
    sandbox: SandboxProtocol,
    timeout_seconds: Optional[float] = None,
) -> ToolResult:
    """
    便捷函数：快速执行 Python 代码（使用内存索引）

    适用于简单场景，无需手动管理 index_store
    """
    index_store = InMemoryIndexStore()
    return await execute_python(
        code=code,
        sandbox=sandbox,
        index_store=index_store,
        timeout_seconds=timeout_seconds,
    )
