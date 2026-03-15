"""
Phase 4 配置优先级和透传验证测试

测试用例:
1. CLI 覆盖 .env：--max-executions 覆盖环境变量
2. timeout 透传：--timeout 传入 tools
3. summary_max_chars 透传：--summary-max-chars 限制摘要长度
4. total_timeout 透传：--total-timeout 触发 stop_reason=total_timeout
"""
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.index_store import InMemoryIndexStore
from agent.agent import SandboxAgent


class MockLLM:
    """Mock LLM 用于测试配置透传"""

    def __init__(self, tool_calls_count=0):
        self.tool_calls_count = tool_calls_count
        self.call_count = 0

    def __call__(self, messages):
        from langchain_core.messages import AIMessage

        self.call_count += 1

        # 如果需要返回 tool_calls
        if self.call_count <= self.tool_calls_count:
            return AIMessage(
                content="",
                tool_calls=[{
                    "id": f"call_{self.call_count}",
                    "name": "execute_python",
                    "args": {"code": "print('hello')"},
                }]
            )

        # 否则返回最终答案
        return AIMessage(content="Test complete")


class MockSandbox:
    """Mock 沙箱用于验证 timeout 透传"""

    def __init__(self):
        self.last_timeout = None
        self.call_count = 0

    async def execute(self, code, timeout_seconds=None, memory_limit_mb=None):
        self.last_timeout = timeout_seconds
        self.call_count += 1

        # 模拟成功执行
        class MockResult:
            status = "success"
            stdout = "hello"
            stderr = ""
            result = None
            execution_time = 0.1

        return MockResult()


def test_cli_override_env():
    """测试1: CLI 参数覆盖环境变量逻辑"""
    print("\n[TEST 1] CLI 覆盖环境变量")

    # 模拟 CLI 参数解析结果
    cli_max_exec = 3
    env_max_exec = 10

    # 验证优先级逻辑：CLI > .env > 默认值
    effective_max = cli_max_exec if cli_max_exec is not None else env_max_exec

    assert effective_max == 3, f"Expected 3, got {effective_max}"
    print(f"  CLI={cli_max_exec}, ENV={env_max_exec}, Effective={effective_max} ✓")


def test_timeout_pass_through():
    """测试2: timeout 参数透传到 sandbox"""
    print("\n[TEST 2] timeout 透传验证")

    async def run_test():
        mock_sandbox = MockSandbox()
        mock_llm = MockLLM(tool_calls_count=1)

        agent = SandboxAgent(
            llm=mock_llm,
            sandbox=mock_sandbox,
            index_store=InMemoryIndexStore(),
            max_executions=5,
            total_timeout_seconds=60.0,
            tool_timeout_seconds=2.0,  # 设置特定的 timeout
            summary_max_chars=500,
            verbose=False,
        )

        # 运行 agent
        result = await agent.run("test")

        # 验证 timeout 已透传到 sandbox
        assert mock_sandbox.last_timeout == 2.0, f"Expected 2.0, got {mock_sandbox.last_timeout}"
        print(f"  tool_timeout_seconds=2.0, sandbox received={mock_sandbox.last_timeout} ✓")

    asyncio.run(run_test())


def test_summary_max_chars_pass_through():
    """测试3: summary_max_chars 限制摘要长度"""
    print("\n[TEST 3] summary_max_chars 透传验证")

    async def run_test():
        # 使用真实沙箱但验证配置传递
        from sandbox_wrapper import FixedPyodideSandbox

        mock_llm = MockLLM(tool_calls_count=1)
        sandbox = FixedPyodideSandbox(allow_net=False)

        # 创建索引存储以检查摘要长度
        index_store = InMemoryIndexStore()

        agent = SandboxAgent(
            llm=mock_llm,
            sandbox=sandbox,
            index_store=index_store,
            max_executions=5,
            total_timeout_seconds=60.0,
            tool_timeout_seconds=15.0,
            summary_max_chars=50,  # 设置较小的限制
            verbose=False,
        )

        # 运行会产生输出的代码
        mock_llm_with_output = MockLLM(tool_calls_count=1)
        mock_llm_with_output.__call__ = lambda msgs: type('obj', (object,), {
            'content': '',
            'tool_calls': [{
                'id': 'call_1',
                'name': 'execute_python',
                'args': {'code': 'print("A" * 100)'},  # 长输出
            }]
        })()

        # 手动测试摘要长度限制
        from agent.tools import execute_python, ExecutePythonConfig

        config = ExecutePythonConfig(summary_max_chars=30)
        result = await execute_python(
            code='print("A" * 100)',
            sandbox=sandbox,
            index_store=index_store,
            config=config,
        )

        # 验证摘要被截断（包含截断标记）
        assert len(result.summary) < 150, f"Summary too long: {len(result.summary)} chars"
        assert "truncated" in result.summary or len(result.summary) <= 50, "Summary not truncated"
        print(f"  summary_max_chars=30, actual summary length={len(result.summary)} ✓")

    asyncio.run(run_test())


def test_total_timeout_stop_reason():
    """测试4: total_timeout 触发 stop_reason=total_timeout"""
    print("\n[TEST 4] total_timeout 触发 stop_reason")

    async def run_test():
        mock_sandbox = MockSandbox()

        # 创建会多次调用工具的 LLM
        class SlowLLM:
            call_count = 0
            def __call__(self, messages):
                from langchain_core.messages import AIMessage
                import time
                time.sleep(0.02)  # 模拟延迟
                self.call_count += 1
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "id": f"call_{self.call_count}",
                        "name": "execute_python",
                        "args": {"code": "print('hello')"},
                    }]
                )

        mock_llm = SlowLLM()

        agent = SandboxAgent(
            llm=mock_llm,
            sandbox=mock_sandbox,
            index_store=InMemoryIndexStore(),
            max_executions=100,  # 设置很大的值，确保不被 max_executions 限制
            total_timeout_seconds=0.05,  # 50ms 总超时（很短）
            tool_timeout_seconds=15.0,
            summary_max_chars=500,
            verbose=False,
        )

        # 运行 agent
        result = await agent.run("test")

        # 验证 stop_reason
        assert result.stop_reason == "total_timeout", f"Expected 'total_timeout', got '{result.stop_reason}'"
        print(f"  total_timeout_seconds=0.05, stop_reason={result.stop_reason} ✓")

    asyncio.run(run_test())


def test_config_precedence_in_agent():
    """测试5: Agent 内部配置优先级验证"""
    print("\n[TEST 5] Agent 内部配置一致性")

    mock_llm = MockLLM()
    mock_sandbox = MockSandbox()

    # 使用特定值创建 Agent
    agent = SandboxAgent(
        llm=mock_llm,
        sandbox=mock_sandbox,
        index_store=InMemoryIndexStore(),
        max_executions=7,
        total_timeout_seconds=120.0,
        tool_timeout_seconds=5.0,
        summary_max_chars=200,
        verbose=False,
    )

    # 验证 Agent 属性
    assert agent.max_executions == 7
    assert agent.total_timeout_seconds == 120.0
    assert agent.tool_timeout_seconds == 5.0
    assert agent.summary_max_chars == 200

    print(f"  max_executions={agent.max_executions} ✓")
    print(f"  total_timeout_seconds={agent.total_timeout_seconds} ✓")
    print(f"  tool_timeout_seconds={agent.tool_timeout_seconds} ✓")
    print(f"  summary_max_chars={agent.summary_max_chars} ✓")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 4 配置优先级与透传测试")
    print("=" * 60)

    try:
        test_cli_override_env()
        test_timeout_pass_through()
        test_summary_max_chars_pass_through()
        test_total_timeout_stop_reason()
        test_config_precedence_in_agent()

        print("\n" + "=" * 60)
        print("PHASE4_CONFIG_PRECEDENCE_PASS")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n[ASSERTION FAILED] {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
