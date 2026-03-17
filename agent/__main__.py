"""
Agent CLI 入口

运行方式：
    python -m agent "计算 1 到 100 的和"
    python -m agent "计算 1 到 100 的和" --max-executions 5 --verbose

环境变量（从 .env 加载）：
    LLM_MODEL: 模型名称 (默认: qwen-plus)
    DASHSCOPE_API_KEY: 阿里云百炼 API Key (必填)
    LLM_BASE_URL: API 基础 URL (默认: https://dashscope.aliyuncs.com/compatible-mode/v1)
    AGENT_MAX_EXECUTIONS: 最大执行轮次 (默认: 10)
    AGENT_TOOL_TIMEOUT_SECONDS: 工具超时 (默认: 15)
    AGENT_SUMMARY_MAX_CHARS: 摘要最大字符数 (默认: 500)
    AGENT_TOTAL_TIMEOUT_SECONDS: 总超时时间 (默认: 60)
    AGENT_ALLOW_NET: 是否允许网络访问 (默认: true)
    AGENT_NO_INDEX: 无索引模式 (默认: false)
    AGENT_EXECUTION_BACKEND: 执行后端 pyodide|local (默认: pyodide)
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 加载 .env 文件
try:
    from dotenv import load_dotenv

    # 从项目根目录加载 .env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 可选


class ConfigError(Exception):
    """配置错误"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"[CONFIG_ERROR] {field}: {reason}")


def validate_config(args) -> dict:
    """
    验证配置并返回参数字典

    优先级: CLI > .env > 默认值

    Raises:
        ConfigError: 配置验证失败
    """
    errors = []

    # 1. 校验 query 不能为空
    query = args.query.strip() if args.query else ""
    if not query:
        errors.append(("query", "不能为空或仅包含空格"))

    # 2. 校验 API_KEY（CLI --api-key > 环境变量 DASHSCOPE_API_KEY）
    api_key = (getattr(args, 'api_key', None) or "").strip()
    if not api_key:
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        errors.append(("DASHSCOPE_API_KEY", "未设置，请通过 --api-key 或 .env 文件设置"))

    # 3. 校验 LLM_MODEL（CLI --model > 环境变量 LLM_MODEL > 默认值）
    model = (getattr(args, 'model', None) or "").strip()
    if not model:
        model = os.getenv("LLM_MODEL", "").strip()
    if not model:
        model = "qwen-plus"

    # 4. 校验 AGENT_MAX_EXECUTIONS（CLI 参数覆盖环境变量）
    max_exec = args.max_executions
    if max_exec is None:
        max_exec_str = os.getenv("AGENT_MAX_EXECUTIONS", "10").strip()
        try:
            max_exec = int(max_exec_str)
        except ValueError:
            errors.append(("AGENT_MAX_EXECUTIONS", f"必须是整数，当前值: {max_exec_str}"))

    if max_exec is not None and max_exec <= 0:
        errors.append(("AGENT_MAX_EXECUTIONS", f"必须是正整数，当前值: {max_exec}"))

    # 5. 校验 AGENT_TOOL_TIMEOUT_SECONDS（CLI 参数覆盖环境变量）
    timeout = args.timeout
    if timeout is None:
        timeout_str = os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "15").strip()
        try:
            timeout = int(timeout_str)
            if timeout <= 0:
                errors.append(("AGENT_TOOL_TIMEOUT_SECONDS", f"必须 > 0，当前值: {timeout}"))
        except ValueError:
            errors.append(("AGENT_TOOL_TIMEOUT_SECONDS", f"必须是数字，当前值: {timeout_str}"))

    if timeout is not None and timeout <= 0:
        errors.append(("AGENT_TOOL_TIMEOUT_SECONDS", f"必须 > 0，当前值: {timeout}"))

    # 6. 校验 AGENT_SUMMARY_MAX_CHARS（CLI 参数覆盖环境变量）
    summary_chars = args.summary_max_chars
    if summary_chars is None:
        summary_chars_str = os.getenv("AGENT_SUMMARY_MAX_CHARS", "2000").strip()
        try:
            summary_chars = int(summary_chars_str)
        except ValueError:
            errors.append(("AGENT_SUMMARY_MAX_CHARS", f"必须是整数，当前值: {summary_chars_str}"))

    if summary_chars is not None and summary_chars <= 0:
        errors.append(("AGENT_SUMMARY_MAX_CHARS", f"必须 > 0，当前值: {summary_chars}"))

    # 7. 校验 AGENT_TOTAL_TIMEOUT_SECONDS（CLI 参数覆盖环境变量）
    total_timeout = args.total_timeout
    if total_timeout is None:
        total_timeout_str = os.getenv("AGENT_TOTAL_TIMEOUT_SECONDS", "60").strip()
        try:
            total_timeout = float(total_timeout_str)
            if total_timeout <= 0:
                errors.append(("AGENT_TOTAL_TIMEOUT_SECONDS", f"必须 > 0，当前值: {total_timeout}"))
        except ValueError:
            errors.append(("AGENT_TOTAL_TIMEOUT_SECONDS", f"必须是数字，当前值: {total_timeout_str}"))

    if total_timeout is not None and total_timeout <= 0:
        errors.append(("AGENT_TOTAL_TIMEOUT_SECONDS", f"必须 > 0，当前值: {total_timeout}"))

    # 如果有错误，抛出第一个
    if errors:
        field, reason = errors[0]
        raise ConfigError(field, reason)

    return {
        "query": query,
        "api_key": api_key,
        "model": model,
        "base_url": (getattr(args, 'base_url', None) or "").strip() or os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").strip(),
        "max_executions": max_exec or 10,
        "tool_timeout_seconds": float(timeout or 15),
        "summary_max_chars": summary_chars or 2000,
        "total_timeout_seconds": float(total_timeout or 60),
        "allow_net": os.getenv("AGENT_ALLOW_NET", "true").lower() == "true",
        "no_index": args.no_index or os.getenv("AGENT_NO_INDEX", "false").lower() == "true",
        "no_fetch_tool": getattr(args, "no_fetch_tool", False),
        "execution_backend": os.getenv("AGENT_EXECUTION_BACKEND", "pyodide").strip().lower(),
        "verbose": args.verbose,
    }


def create_llm_callable(config: dict):
    """
    创建 LLM 调用函数（使用 OpenAI 兼容接口）

    根据配置返回一个可调用对象，接收 messages 列表返回 AIMessage
    """
    api_key = config["api_key"]
    model = config["model"]
    base_url = config["base_url"]

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field

        # 定义工具输入 schema
        class CodeExecutionInput(BaseModel):
            code: str = Field(description="Python 代码字符串，用于在沙箱中执行")

        class ReadFileInput(BaseModel):
            path: str = Field(description="相对工作区根目录的文件路径")
            max_chars: int = Field(default=12000, description="读取内容最大字符数")

        class WriteFileInput(BaseModel):
            path: str = Field(description="相对工作区根目录的文件路径")
            content: str = Field(description="要写入的完整文件内容")

        class ExecutionDetailInput(BaseModel):
            execution_id: Optional[str] = Field(
                default=None,
                description="要查询的执行ID（从 execute_python 返回结果中获取）。不传则查询最近一次执行。",
            )
            max_chars: int = Field(
                default=4000,
                description="返回详情的最大字符数",
            )

        # 创建工具定义（实际执行由工作流处理）
        execute_python_tool = StructuredTool.from_function(
            func=lambda code: code,  # 占位函数，实际执行在工作流中处理
            name="execute_python",
            description="在沙箱环境中执行 Python 代码。当你需要运行代码计算、处理数据或验证结果时，使用此工具。",
            args_schema=CodeExecutionInput,
            return_direct=False,
        )

        read_file_tool = StructuredTool.from_function(
            func=lambda path, max_chars=12000: {"path": path, "max_chars": max_chars},
            name="read_file",
            description="读取工作区内文件内容，用于理解和定位代码问题。",
            args_schema=ReadFileInput,
            return_direct=False,
        )

        write_file_tool = StructuredTool.from_function(
            func=lambda path, content: {"path": path, "content": content},
            name="write_file",
            description="写入工作区内文件内容（覆盖写入），用于修复或重构代码。",
            args_schema=WriteFileInput,
            return_direct=False,
        )

        fetch_execution_detail_tool = StructuredTool.from_function(
            func=lambda execution_id=None, max_chars=4000: {
                "execution_id": execution_id,
                "max_chars": max_chars,
            },
            name="fetch_execution_detail",
            description=(
                "查询历史执行的完整详情（stdout/stderr/result）。\n\n"
                "⚠️ 调用前先检查：execute_python 返回的摘要已包含 Error Type / Error Message / Error Location。\n"
                "如果这些结构化字段已足够诊断问题（如 ModuleNotFoundError、SyntaxError、NameError），\n"
                "请直接修复代码并重新执行，无需调用此工具。\n\n"
                "仅在以下情况调用：\n"
                "1. 错误摘要中缺少 Error Type/Message，无法判断问题原因\n"
                "2. status: success 但需要摘要中不可见的精确数值进行后续计算\n\n"
                "用法：\n"
                "- execution_id: 要查询的执行ID（从 execute_python 返回结果中获取）\n"
                "- 如果不传 execution_id，默认查询最近一次执行"
            ),
            args_schema=ExecutionDetailInput,
            return_direct=False,
        )

        # 根据模式决定绑定哪些工具
        # CM：绑定 fetch_execution_detail
        # Baseline（no_fetch_tool）：有索引/压缩，但不暴露 fetch 工具
        # Native（no_index）：无索引，不暴露 fetch 工具
        tools = [read_file_tool, write_file_tool, execute_python_tool]
        if not config.get("no_index", False) and not config.get("no_fetch_tool", False):
            tools.append(fetch_execution_detail_tool)

        # 使用 LangChain 的 ChatOpenAI，绑定工具支持
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
        ).bind_tools(tools)

        def llm_callable(messages):
            return llm.invoke(messages)

        return llm_callable

    except ImportError:
        raise ConfigError(
            "LLM_CLIENT",
            "OpenAI 兼容客户端未安装，请运行: pip install langchain-openai"
        )


def create_sandbox(config: dict):
    """创建沙箱实例"""
    backend = config.get("execution_backend", "pyodide")
    if backend == "local":
        from local_sandbox import LocalPythonSandbox

        workspace_root = str(Path(__file__).parent.parent)
        return LocalPythonSandbox(workspace_root=workspace_root)

    if backend == "pyodide":
        try:
            from sandbox_wrapper import FixedPyodideSandbox

            return FixedPyodideSandbox(allow_net=config["allow_net"])
        except ImportError:
            raise ConfigError(
                "SANDBOX",
                "无法加载 FixedPyodideSandbox，请确认 langchain-sandbox 已安装"
            )

    raise ConfigError("AGENT_EXECUTION_BACKEND", f"不支持的执行后端: {backend}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Sandbox Agent - 基于沙箱的代码执行 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python -m agent "计算 1 到 100 的和"
    python -m agent "计算 1 到 100 的和" --max-executions 5 --verbose

环境变量:
    DASHSCOPE_API_KEY   必填: 阿里云百炼 API Key
    LLM_MODEL           可选: 模型名称 (默认: qwen-plus)
    LLM_BASE_URL        可选: API 基础 URL (默认: 阿里云百炼)
    AGENT_MAX_EXECUTIONS 可选: 最大执行轮次 (默认: 10)
        """,
    )

    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        help="用户问题（必填）",
    )

    parser.add_argument(
        "--max-executions",
        type=int,
        default=None,
        help="最大工具执行轮次（覆盖环境变量）",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="工具执行超时时间（秒，覆盖环境变量）",
    )

    parser.add_argument(
        "--total-timeout",
        type=float,
        default=None,
        help="Agent 总超时时间（秒，覆盖环境变量）",
    )

    parser.add_argument(
        "--summary-max-chars",
        type=int,
        default=None,
        help="摘要最大字符数（覆盖环境变量）",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM 模型名称（覆盖环境变量 LLM_MODEL）",
    )

    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="LLM API 基础 URL（覆盖环境变量 LLM_BASE_URL）",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="LLM API Key（覆盖环境变量 DASHSCOPE_API_KEY）",
    )

    parser.add_argument(
        "--no-index",
        action="store_true",
        help="无索引模式：跳过执行结果存储（AGENT_NO_INDEX=true 等效）",
    )

    parser.add_argument(
        "--no-fetch-tool",
        action="store_true",
        help="压缩模式：启用索引与消息压缩，但不向 LLM 暴露 fetch_execution_detail 工具（Baseline 模式）",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="打印诊断日志（默认开启）",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，不打印诊断日志",
    )

    args = parser.parse_args()

    # 处理 --quiet
    if args.quiet:
        args.verbose = False

    # 如果没有提供 query，打印帮助
    if not args.query:
        parser.print_help()
        print("\n[CONFIG_ERROR] query: 不能为空，请提供用户问题")
        print("\n修复方法: 在命令后添加要询问的问题，例如:")
        print('  python -m agent "计算 1 到 100 的和"')
        sys.exit(1)

    try:
        # 验证配置
        config = validate_config(args)

        # 设置日志级别
        if config["verbose"]:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.WARNING)

        logger.info(f"event=agent_start model={config['model']} max_executions={config['max_executions']}")
        logger.debug(f"event=config_loaded tool_timeout={config['tool_timeout_seconds']}s total_timeout={config['total_timeout_seconds']}s")

        # 创建组件
        llm = create_llm_callable(config)
        sandbox = create_sandbox(config)

        from agent import SandboxAgent, InMemoryIndexStore
        from agent.index_store import NoOpIndexStore

        index_store = NoOpIndexStore() if config["no_index"] else InMemoryIndexStore()

        # has_fetch_tool: False if no_index (native) or no_fetch_tool (baseline), True for CM
        has_fetch_tool = not config["no_index"] and not config.get("no_fetch_tool", False)

        agent = SandboxAgent(
            llm=llm,
            sandbox=sandbox,
            index_store=index_store,
            max_executions=config["max_executions"],
            total_timeout_seconds=config["total_timeout_seconds"],
            tool_timeout_seconds=config["tool_timeout_seconds"],
            summary_max_chars=config["summary_max_chars"],
            verbose=config["verbose"],
            has_fetch_tool=has_fetch_tool,
        )

        # 运行 Agent
        result = await agent.run(config["query"])

        # 输出结果
        print("\n" + "=" * 50)
        print("最终答案:")
        print("=" * 50)
        print(result.answer)

        # Phase 1: 准备指标数据
        idx_mode = 'no-index' if config['no_index'] else ('baseline' if config.get('no_fetch_tool') else 'context-mode')
        avg_tool_summary_chars = (
            (sum(m.get("summary_chars", 0) for m in (result.tool_metrics or [])) / len(result.tool_metrics))
            if result.tool_metrics
            else 0.0
        )

        logger.info(
            "event=agent_complete execution_count=%s stop_reason=%s index_mode=%s llm_prompt_tokens=%s llm_completion_tokens=%s llm_total_tokens=%s max_prompt_tokens=%s elapsed_seconds=%.3f tool_calls=%s avg_tool_summary_chars=%.1f",
            result.execution_count,
            result.stop_reason,
            idx_mode,
            result.llm_prompt_tokens,
            result.llm_completion_tokens,
            result.llm_total_tokens,
            result.max_prompt_tokens,
            result.elapsed_seconds,
            len(result.tool_metrics or []),
            avg_tool_summary_chars,
        )

        if config["verbose"]:
            print("\n" + "-" * 50)
            print(f"执行统计:")
            print(f"  - 工具调用次数: {result.execution_count}")
            print(f"  - 最后执行ID: {result.last_execution_id or 'N/A'}")
            print(f"  - 停止原因: {result.stop_reason or '正常完成'}")
            print(f"  - 索引模式: {idx_mode}")
            print(f"  - LLM tokens(prompt/completion/total): {result.llm_prompt_tokens}/{result.llm_completion_tokens}/{result.llm_total_tokens}")
            print(f"  - 最大单轮 prompt tokens: {result.max_prompt_tokens}")
            print(f"  - 总耗时(秒): {result.elapsed_seconds:.3f}")
            # Phase 1: 新增用户体验指标
            print(f"  - 任务成功: {result.task_success}")
            print(f"  - 消息压缩比: {result.compression_ratio:.2%}")
            print(f"  - fetch调用次数: {result.fetch_hit_count}")
            print(f"  - 平均LLM延迟: {sum(result.per_round_llm_latency or [0]) / max(len(result.per_round_llm_latency or []), 1):.3f}s")
            print(f"  - 平均工具延迟: {sum(result.per_round_tool_latency or [0]) / max(len(result.per_round_tool_latency or []), 1):.3f}s")

        # Phase 1: 输出结构化指标（供 main.py 解析）
        import json as _json
        print(f"\nROUND_TOKEN_HISTORY_JSON:{_json.dumps(result.round_token_history or [])}")
        _metrics = {
            "execution_count": result.execution_count,
            "stop_reason": result.stop_reason,
            "elapsed_seconds": result.elapsed_seconds,
            "llm_prompt_tokens": result.llm_prompt_tokens,
            "llm_completion_tokens": result.llm_completion_tokens,
            "llm_total_tokens": result.llm_total_tokens,
            "max_prompt_tokens": result.max_prompt_tokens,
            "task_success": result.task_success,
            "compression_ratio": result.compression_ratio,
            "fetch_hit_count": result.fetch_hit_count,
            "per_round_llm_latency": result.per_round_llm_latency,
            "per_round_tool_latency": result.per_round_tool_latency,
        }
        print(f"METRICS_JSON:{_json.dumps(_metrics)}")

        return 0

    except ConfigError as e:
        logger.error(f"event=config_error field={e.field} reason={e.reason}")
        print(f"\n[CONFIG_ERROR] {e.field}: {e.reason}")
        print("\n修复方法: 请检查 .env 文件或环境变量设置")
        sys.exit(1)

    except Exception as e:
        logger.error(f"event=runtime_error error_type={type(e).__name__} error_message={str(e)}")
        print(f"\n[ERROR] 运行时错误: {type(e).__name__}: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
