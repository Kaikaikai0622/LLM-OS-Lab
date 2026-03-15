"""
Phase 3 多 tool_calls 冒烟测试

验证单轮多 tool_calls 顺序执行能力
运行方式：python tests/smoke_phase3_multi_toolcalls.py
"""
import sys
import asyncio
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

sys.path.insert(0, "d:/Code/my-sandbox-demo")

from agent import (
    SandboxAgent,
    InMemoryIndexStore,
)

class FakeLLM:
    """Fake LLM，按预设脚本返回响应"""

    def __init__(self, script: list[dict]):
        self.script = script
        self.call_count = 0

    def __call__(self, messages: list) -> AIMessage:
        """模拟 LLM 调用"""
        if self.call_count < len(self.script):
            response_data = self.script[self.call_count]
            self.call_count += 1

            tool_calls = response_data.get("tool_calls", [])
            content = response_data.get("content", "")

            # 格式化 tool_calls 为 LangChain 兼容结构
            formatted_tool_calls = []
            for i, tc in enumerate(tool_calls):
                name = tc.get("name") or tc.get("function", {}).get("name", "execute_python")
                args = tc.get("args")
                if args is None:
                    args = tc.get("arguments")
                if args is None:
                    args = tc.get("function", {}).get("arguments", {})

                formatted_tc = {
                    "id": tc.get("id", f"call_{self.call_count}_{i}"),
                    "name": name,
                    "args": args,
                    "type": tc.get("type", "tool_call"),
                }
                formatted_tool_calls.append(formatted_tc)

            return AIMessage(
                content=content,
                tool_calls=formatted_tool_calls,
            )
        else:
            return AIMessage(content="Default final answer")


@dataclass
class FakeSandboxResult:
    """Fake 沙箱返回结果"""
    status: str
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    execution_time: float = 1.0


class FakeSandbox:
    """Fake 沙箱"""

    def __init__(self, behavior: str = "success", stdout: str = "", stderr: str = ""):
        self.behavior = behavior
        self.stdout = stdout
        self.stderr = stderr
        self.execution_order: list[str] = []  # 记录执行顺序

    async def execute(self, code: str, **kwargs) -> FakeSandboxResult:
        # 记录执行顺序（通过代码内容识别）
        if "first" in code.lower():
            self.execution_order.append("first")
        elif "second" in code.lower():
            self.execution_order.append("second")
        else:
            self.execution_order.append("unknown")

        return FakeSandboxResult(
            status=self.behavior,
            stdout=self.stdout,
            stderr=self.stderr,
            result=None if self.behavior == "error" else "mock_result",
            execution_time=1.0,
        )


async def run_tests():
    """运行多 tool_calls 冒烟测试"""
    passed = 0
    failed = 0

    print("=" * 50)
    print("Phase 3 多 tool_calls 冒烟测试")
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

    # === 用例：单轮返回 2 个 tool_calls ===
    print("\n用例：单轮返回 2 个 tool_calls")
    print("-" * 50)

    llm = FakeLLM([
        {
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "execute_python",
                        "arguments": {"code": "print('first')"},
                    },
                },
                {
                    "id": "call_2",
                    "function": {
                        "name": "execute_python",
                        "arguments": {"code": "print('second')"},
                    },
                },
            ],
        },
        {"content": "Both tools executed successfully"},
    ])
    sandbox = FakeSandbox(behavior="success", stdout="executed")
    store = InMemoryIndexStore()

    agent = SandboxAgent(
        llm=llm,
        sandbox=sandbox,
        index_store=store,
        max_executions=10,
        verbose=True,
    )

    result = await agent.run("Execute multiple tools")

    # 断言 1: execution_count == 2（两个 tool_calls 都执行了）
    test(
        "execution_count == 2",
        result.execution_count == 2,
        f"execution_count={result.execution_count}, expected=2",
    )

    # 断言 2: 顺序执行（先执行 first，再执行 second）
    test(
        "tool_calls 按顺序执行",
        sandbox.execution_order == ["first", "second"],
        f"execution_order={sandbox.execution_order}",
    )

    # 断言 3: 存在 2 条 ToolMessage
    tool_messages = [m for m in result.messages if isinstance(m, ToolMessage)]
    test(
        "存在 2 条 ToolMessage",
        len(tool_messages) == 2,
        f"tool_messages count={len(tool_messages)}, expected=2",
    )

    # 断言 4: ToolMessage 有正确的 tool_call_id
    test(
        "第一条 ToolMessage 关联 call_1",
        len(tool_messages) >= 1 and tool_messages[0].tool_call_id == "call_1",
        f"tool_call_id={tool_messages[0].tool_call_id if tool_messages else 'N/A'}",
    )
    test(
        "第二条 ToolMessage 关联 call_2",
        len(tool_messages) >= 2 and tool_messages[1].tool_call_id == "call_2",
        f"tool_call_id={tool_messages[1].tool_call_id if len(tool_messages) > 1 else 'N/A'}",
    )

    # 断言 5: 正常结束，不是被限制停止
    test(
        "正常结束，stopped_by_limit 为 False",
        not result.stopped_by_limit,
        f"stopped_by_limit={result.stopped_by_limit}",
    )
    test(
        "stop_reason 为 no_tool_calls",
        result.stop_reason == "no_tool_calls",
        f"stop_reason={result.stop_reason}",
    )

    # 断言 6: 最终答案正确
    test(
        "最终答案存在",
        "Both tools" in result.answer,
        f"answer={result.answer}",
    )

    # === 测试汇总 ===
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\nPHASE3_MULTI_TOOLCALLS_PASS")
        return 0
    else:
        print(f"\nPHASE3_MULTI_TOOLCALLS_FAIL ({failed} failed)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
