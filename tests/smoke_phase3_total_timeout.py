"""
Phase 3 总超时冒烟测试

验证 total_timeout_seconds 超时机制
运行方式：python tests/smoke_phase3_total_timeout.py
"""
import sys
import asyncio
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage

sys.path.insert(0, "d:/Code/my-sandbox-demo")

from agent import (
    SandboxAgent,
    InMemoryIndexStore,
)

class FakeLLM:
    """Fake LLM，持续返回 tool_calls"""

    def __init__(self, num_calls: int = 100):
        self.num_calls = num_calls
        self.call_count = 0

    def __call__(self, messages: list) -> AIMessage:
        """模拟 LLM 调用，永远返回 tool_call"""
        self.call_count += 1

        return AIMessage(
            content="",
            tool_calls=[{
                "id": f"call_{self.call_count}",
                "name": "execute_python",
                "args": {"code": f"print('call {self.call_count}')"},
                "type": "tool_call",
            }],
        )


@dataclass
class FakeSandboxResult:
    """Fake 沙箱返回结果"""
    status: str
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    execution_time: float = 1.0


class FakeSandbox:
    """Fake 沙箱 - 带延迟模拟"""

    def __init__(self, delay: float = 0.01):
        self.delay = delay

    async def execute(self, code: str, **kwargs) -> FakeSandboxResult:
        # 模拟执行延迟
        await asyncio.sleep(self.delay)
        return FakeSandboxResult(
            status="success",
            stdout="executed",
            stderr="",
            result="mock_result",
            execution_time=self.delay,
        )


async def run_tests():
    """运行总超时冒烟测试"""
    passed = 0
    failed = 0

    print("=" * 50)
    print("Phase 3 总超时冒烟测试")
    print("=" * 50)

    def test(name: str, condition: bool, context: str = ""):
        nonlocal passed, failed
        print(f"[CASE] {name}")
        if condition:
            print(f"[OK]")
            passed += 1
        else:
            print(f"[FAIL] {context}")
            failed += 1

    # === 用例：total_timeout 超时触发 ===
    print("\n用例：total_timeout 超时触发")
    print("-" * 50)

    # 使用极小的超时时间（0.05秒）
    timeout_seconds = 0.05

    llm = FakeLLM(num_calls=100)  # 会持续返回 tool_calls
    sandbox = FakeSandbox(delay=0.01)  # 每次执行 0.01 秒
    store = InMemoryIndexStore()

    agent = SandboxAgent(
        llm=llm,
        sandbox=sandbox,
        index_store=store,
        max_executions=100,  # 设置很大的 max_executions，让 timeout 先触发
        total_timeout_seconds=timeout_seconds,
        verbose=True,
    )

    start_time = time.monotonic()
    result = await agent.run("Infinite task with timeout")
    elapsed = time.monotonic() - start_time

    # 断言 1: 实际耗时应该接近 timeout_seconds（略大于或等于）
    test(
        f"实际耗时约 {timeout_seconds}s (实际: {elapsed:.3f}s)",
        elapsed >= timeout_seconds and elapsed < timeout_seconds + 0.5,
        f"elapsed={elapsed:.3f}s",
    )

    # 断言 2: stop_reason 必须是 total_timeout
    test(
        "stop_reason == 'total_timeout'",
        result.stop_reason == "total_timeout",
        f"stop_reason={result.stop_reason}",
    )

    # 断言 3: stopped_by_limit 应该为 True（超时也算限制）
    test(
        "stopped_by_limit 为 True",
        result.stopped_by_limit,
        f"stopped_by_limit={result.stopped_by_limit}",
    )

    # 断言 4: 没有达到 max_executions（证明是超时停止的）
    test(
        "execution_count < max_executions",
        result.execution_count < 100,
        f"execution_count={result.execution_count}, max_executions=100",
    )

    # === 用例：max_executions 先于 timeout 触发 ===
    print("\n用例：max_executions 先于 timeout 触发")
    print("-" * 50)

    llm2 = FakeLLM(num_calls=100)
    sandbox2 = FakeSandbox(delay=0.001)  # 更快的执行
    store2 = InMemoryIndexStore()

    agent2 = SandboxAgent(
        llm=llm2,
        sandbox=sandbox2,
        index_store=store2,
        max_executions=3,  # 很小的 max_executions
        total_timeout_seconds=10.0,  # 很大的 timeout
        verbose=True,
    )

    result2 = await agent2.run("Limited executions")

    # 断言 1: execution_count 应该等于 max_executions
    test(
        "execution_count == max_executions (3)",
        result2.execution_count == 3,
        f"execution_count={result2.execution_count}",
    )

    # 断言 2: stop_reason 应该是 max_executions（不是 timeout）
    test(
        "stop_reason == 'max_executions'",
        result2.stop_reason == "max_executions",
        f"stop_reason={result2.stop_reason}",
    )

    # 断言 3: stopped_by_limit 为 True
    test(
        "stopped_by_limit 为 True",
        result2.stopped_by_limit,
        f"stopped_by_limit={result2.stopped_by_limit}",
    )

    # === 测试汇总 ===
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\nPHASE3_TOTAL_TIMEOUT_PASS")
        return 0
    else:
        print(f"\nPHASE3_TOTAL_TIMEOUT_FAIL ({failed} failed)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
