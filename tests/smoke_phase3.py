"""
Phase 3 冒烟测试

验证工作流状态迁移、分支判断和终止逻辑
运行方式：python tests/smoke_phase3.py
"""
import sys
import asyncio
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage

sys.path.insert(0, "d:/Code/my-sandbox-demo")

from agent import (
    SandboxAgent,
    InMemoryIndexStore,
    NoOpIndexStore,
)


class FakeLLM:
    """
    Fake LLM，按预设脚本返回响应

    使用示例：
        script = [
            {"tool_calls": [{"function": {"name": "execute_python", "arguments": {"code": "print(1)"}}}]},
            {"content": "Final answer: 1"},
        ]
        llm = FakeLLM(script)
    """

    def __init__(self, script: list[dict]):
        """
        Args:
            script: 响应脚本列表，每个元素是一个 dict
                   可包含 content 和/或 tool_calls
        """
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
            # 脚本结束后默认返回结束消息
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

    async def execute(self, code: str, **kwargs) -> FakeSandboxResult:
        return FakeSandboxResult(
            status=self.behavior,
            stdout=self.stdout,
            stderr=self.stderr,
            result=None if self.behavior == "error" else "mock_result",
            execution_time=1.0,
        )


async def run_tests():
    """运行所有冒烟测试用例"""
    passed = 0
    failed = 0

    print("=" * 50)
    print("Phase 3 冒烟测试")
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

    # === 用例 1：直接结束路径（无工具调用）===
    print("\n用例 1：直接结束路径（无工具调用）")
    print("-" * 50)

    llm1 = FakeLLM([
        {"content": "This is the final answer without tool"},
    ])
    sandbox1 = FakeSandbox()
    store1 = InMemoryIndexStore()

    agent1 = SandboxAgent(
        llm=llm1,
        sandbox=sandbox1,
        index_store=store1,
        max_executions=10,
        verbose=True,
    )

    result1 = await agent1.run("Hello")

    test(
        "execution_count == 0",
        result1.execution_count == 0,
        f"execution_count={result1.execution_count}",
    )

    test(
        "最终 answer 存在",
        "final answer" in result1.answer.lower() or result1.answer != "",
        f"answer={result1.answer}",
    )

    # === 用例 2：单轮工具调用 ===
    print("\n用例 2：单轮工具调用")
    print("-" * 50)

    llm2 = FakeLLM([
        {
            "tool_calls": [{
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "print('hello')"},
                },
            }],
        },
        {"content": "The result is hello"},
    ])
    sandbox2 = FakeSandbox(behavior="success", stdout="hello")
    store2 = InMemoryIndexStore()

    agent2 = SandboxAgent(
        llm=llm2,
        sandbox=sandbox2,
        index_store=store2,
        max_executions=10,
        verbose=True,
    )

    result2 = await agent2.run("Print hello")

    test(
        "execution_count == 1",
        result2.execution_count == 1,
        f"execution_count={result2.execution_count}",
    )

    test(
        "last_execution_id 存在",
        result2.last_execution_id is not None,
        f"last_execution_id={result2.last_execution_id}",
    )

    # 使用 agent 内部的 index_store 检索记录
    record_from_store = agent2.index_store.get(result2.last_execution_id) if result2.last_execution_id else None
    test(
        "可通过 execution_id 检索原始记录",
        result2.last_execution_id is not None and record_from_store is not None,
        f"record={record_from_store}",
    )

    # === 用例 3：多轮调用收敛 ===
    print("\n用例 3：多轮调用收敛")
    print("-" * 50)

    llm3 = FakeLLM([
        {
            "tool_calls": [{
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "x = 1 + 1"},
                },
            }],
        },
        {
            "tool_calls": [{
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "y = x * 2"},
                },
            }],
        },
        {"content": "Final answer after two rounds"},
    ])
    sandbox3 = FakeSandbox(behavior="success", stdout="executed")
    store3 = InMemoryIndexStore()

    agent3 = SandboxAgent(
        llm=llm3,
        sandbox=sandbox3,
        index_store=store3,
        max_executions=10,
        verbose=True,
    )

    result3 = await agent3.run("Multi-step task")

    test(
        "execution_count == 2",
        result3.execution_count == 2,
        f"execution_count={result3.execution_count}",
    )

    test(
        "正常结束并有最终答案",
        result3.answer != "" and not result3.stopped_by_limit,
        f"answer={result3.answer}, stopped_by_limit={result3.stopped_by_limit}",
    )

    # === 用例 4：max_executions 保护 ===
    print("\n用例 4：max_executions 保护")
    print("-" * 50)

    # 永远返回 tool_call 的 LLM
    infinite_script = [
        {
            "tool_calls": [{
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "print('infinite')"},
                },
            }],
        },
    ] * 10  # 重复10次

    llm4 = FakeLLM(infinite_script)
    sandbox4 = FakeSandbox(behavior="success", stdout="ok")
    store4 = InMemoryIndexStore()

    agent4 = SandboxAgent(
        llm=llm4,
        sandbox=sandbox4,
        index_store=store4,
        max_executions=2,  # 限制为2轮
        verbose=True,
    )

    result4 = await agent4.run("Infinite task")

    test(
        "execution_count 在 max_executions 处停止",
        result4.execution_count == 2,
        f"execution_count={result4.execution_count}, expected=2",
    )

    test(
        "stopped_by_limit 为 True",
        result4.stopped_by_limit,
        f"stopped_by_limit={result4.stopped_by_limit}",
    )

    # === 用例 5：可追溯性 ===
    print("\n用例 5：可追溯性")
    print("-" * 50)

    llm5 = FakeLLM([
        {
            "tool_calls": [{
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "output = 'test data'\nprint(output)"},
                },
            }],
        },
        {"content": "Done"},
    ])
    sandbox5 = FakeSandbox(behavior="success", stdout="test data")
    store5 = InMemoryIndexStore()

    agent5 = SandboxAgent(
        llm=llm5,
        sandbox=sandbox5,
        index_store=store5,
        max_executions=10,
        verbose=True,
    )

    result5 = await agent5.run("Traceable task")

    # 验证可通过 Agent 方法获取记录
    record5 = agent5.get_execution_record(result5.last_execution_id) if result5.last_execution_id else None

    test(
        "可通过 agent.get_execution_record 获取原始记录",
        record5 is not None,
        f"record={record5}",
    )

    if record5:
        test(
            "原始记录包含完整输出",
            "test" in record5.stdout,
            f"stdout={record5.stdout}",
        )

    # === 用例 6：按需查询执行详情 ===
    print("\n用例 6：按需查询执行详情")
    print("-" * 50)

    llm6 = FakeLLM([
        {
            "tool_calls": [{
                "id": "call_exec",
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "print('detail_hello')"},
                },
            }],
        },
        {
            "tool_calls": [{
                "id": "call_detail",
                "function": {
                    "name": "fetch_execution_detail",
                    "arguments": {},
                },
            }],
        },
        {"content": "Detail fetched"},
    ])
    sandbox6 = FakeSandbox(behavior="success", stdout="detail_hello")
    store6 = InMemoryIndexStore()

    agent6 = SandboxAgent(
        llm=llm6,
        sandbox=sandbox6,
        index_store=store6,
        max_executions=10,
        verbose=True,
    )

    result6 = await agent6.run("Need full detail")

    tool_messages6 = [m for m in result6.messages if getattr(m, "name", "") == "fetch_execution_detail"]
    detail_msg = tool_messages6[-1].content if tool_messages6 else ""

    test(
        "详情查询工具被调用",
        len(tool_messages6) >= 1,
        f"tool_messages_count={len(tool_messages6)}",
    )
    test(
        "详情消息包含 STDOUT",
        "[STDOUT]" in detail_msg and "detail_hello" in detail_msg,
        f"detail_msg={detail_msg[:200]}",
    )

    # === 用例 7：无索引模式下详情查询失败提示 ===
    print("\n用例 7：无索引模式下详情查询")
    print("-" * 50)

    llm7 = FakeLLM([
        {
            "tool_calls": [{
                "id": "call_exec_no_index",
                "function": {
                    "name": "execute_python",
                    "arguments": {"code": "print('no_index')"},
                },
            }],
        },
        {
            "tool_calls": [{
                "id": "call_detail_no_index",
                "function": {
                    "name": "fetch_execution_detail",
                    "arguments": {},
                },
            }],
        },
        {"content": "Handled no-index detail path"},
    ])
    sandbox7 = FakeSandbox(behavior="success", stdout="no_index")
    store7 = NoOpIndexStore()

    agent7 = SandboxAgent(
        llm=llm7,
        sandbox=sandbox7,
        index_store=store7,
        max_executions=10,
        verbose=True,
    )

    result7 = await agent7.run("No index mode")

    tool_messages7 = [m for m in result7.messages if getattr(m, "name", "") == "fetch_execution_detail"]
    detail_msg7 = tool_messages7[-1].content if tool_messages7 else ""

    test(
        "无索引模式详情查询返回 not found",
        "not found" in detail_msg7.lower() or "no-index mode" in detail_msg7.lower(),
        f"detail_msg={detail_msg7[:200]}",
    )

    # === 测试汇总 ===
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\nPHASE3_SMOKE_PASS")
        return 0
    else:
        print(f"\nPHASE3_SMOKE_FAIL ({failed} failed)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
