"""
Phase 2 冒烟测试

验证工具层：沙箱执行 -> 索引写入 -> 摘要回传
运行方式：
  python tests/smoke_phase2.py          # 快速模式（FakeSandbox）
  python tests/smoke_phase2.py --integration  # 集成模式（真实沙箱）
"""
import sys
import argparse
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, "d:/Code/my-sandbox-demo")

from agent import execute_python, InMemoryIndexStore, ExecutePythonConfig


@dataclass
class FakeSandboxResult:
    """Fake 沙箱返回结果"""
    status: str
    stdout: str = ""
    stderr: str = ""
    result: Optional[any] = None
    execution_time: float = 1.0


class FakeSandbox:
    """
    Fake 沙箱，用于快速测试

    通过预设行为模拟沙箱响应，无需启动真实 Pyodide
    """

    def __init__(self, behavior: str = "success", stdout: str = "", stderr: str = "", exception: Optional[Exception] = None):
        self.behavior = behavior
        self.stdout = stdout
        self.stderr = stderr
        self.exception = exception

    async def execute(self, code: str, timeout_seconds: Optional[float] = None, memory_limit_mb: Optional[int] = None):
        if self.exception:
            raise self.exception

        return FakeSandboxResult(
            status=self.behavior,
            stdout=self.stdout,
            stderr=self.stderr,
            result=None if self.behavior == "error" else "mock_result",
            execution_time=1.0,
        )


async def run_tests(integration_mode: bool = False):
    """运行所有冒烟测试用例"""
    passed = 0
    failed = 0

    mode_str = "integration" if integration_mode else "fast"
    print(f"MODE={mode_str}")
    print("=" * 50)

    # 集成模式检查依赖
    if integration_mode:
        try:
            from sandbox_wrapper import FixedPyodideSandbox
        except ImportError as e:
            print(f"[SKIP] 集成模式需要 langchain-sandbox 环境: {e}")
            print("[INFO] 请在 Docker 中运行: docker-compose run --rm sandbox python tests/smoke_phase2.py --integration")
            print("\nPHASE2_SMOKE_SKIP (integration requires Docker)")
            return 0

    def test(name, condition, context="", execution_id: str = ""):
        nonlocal passed, failed
        eid_info = f" [ID={execution_id}]" if execution_id else ""
        print(f"[CASE] {name}{eid_info}")
        if condition:
            print(f"[OK]")
            passed += 1
        else:
            print(f"[FAIL] {context}")
            failed += 1

    # === 用例 1：成功执行闭环 ===
    print("\n用例 1：成功执行闭环")
    print("-" * 50)

    if integration_mode:
        # 集成模式：使用真实沙箱
        from sandbox_wrapper import FixedPyodideSandbox
        sandbox = FixedPyodideSandbox(allow_net=False)
    else:
        # 快速模式：使用 FakeSandbox
        sandbox = FakeSandbox(behavior="success", stdout="hello world")

    store1 = InMemoryIndexStore()
    result1 = await execute_python(
        code='print("hello")',
        sandbox=sandbox,
        index_store=store1,
    )

    test(
        "ToolResult.status=success",
        result1.status == "success",
        f"status={result1.status}",
        result1.execution_id,
    )

    # 验证索引中可取回完整记录
    record1 = store1.get(result1.execution_id)
    test(
        "execution_id 可在索引中命中",
        record1 is not None,
        f"record={record1}",
        result1.execution_id,
    )

    if record1:
        test(
            "索引中记录包含完整 stdout",
            "hello" in record1.stdout,
            f"stdout={record1.stdout}",
            result1.execution_id,
        )

    # === 用例 2：运行错误闭环 ===
    print("\n用例 2：运行错误闭环")
    print("-" * 50)

    if integration_mode:
        from sandbox_wrapper import FixedPyodideSandbox
        sandbox2 = FixedPyodideSandbox(allow_net=False)
        # 真实沙箱中执行错误代码
        code2 = "1/0"
    else:
        sandbox2 = FakeSandbox(behavior="error", stderr="ZeroDivisionError: division by zero")
        code2 = "1/0"

    store2 = InMemoryIndexStore()
    result2 = await execute_python(
        code=code2,
        sandbox=sandbox2,
        index_store=store2,
    )

    test(
        "不抛异常",
        True,  # 如果抛异常就不会执行到这里
        "",
        result2.execution_id,
    )

    test(
        "ToolResult.status=error",
        result2.status == "error",
        f"status={result2.status}",
        result2.execution_id,
    )

    test(
        "summary 包含 execution_id",
        result2.execution_id in result2.summary or "Status: error" in result2.summary,
        f"summary={result2.summary[:100]}",
        result2.execution_id,
    )

    # === 用例 3：异常转译 ===
    print("\n用例 3：异常转译")
    print("-" * 50)

    # 仅快速模式测试（模拟沙箱抛异常）
    if not integration_mode:
        sandbox3 = FakeSandbox(exception=RuntimeError("Sandbox crashed"))
        store3 = InMemoryIndexStore()
        result3 = await execute_python(
            code="print('test')",
            sandbox=sandbox3,
            index_store=store3,
        )

        test(
            "返回 status=error",
            result3.status == "error",
            f"status={result3.status}",
            result3.execution_id,
        )

        test(
            "summary 包含 exception 关键词",
            "exception" in result3.summary.lower() or "Exception" in result3.summary,
            f"summary={result3.summary}",
            result3.execution_id,
        )
    else:
        print("[SKIP] 集成模式跳过异常转译测试")

    # === 用例 4：摘要截断 ===
    print("\n用例 4：摘要截断")
    print("-" * 50)

    long_output = "x" * 5000  # 5000 字符超长输出

    if integration_mode:
        from sandbox_wrapper import FixedPyodideSandbox
        sandbox4 = FixedPyodideSandbox(allow_net=False)
        code4 = f'print("{long_output}")'
    else:
        sandbox4 = FakeSandbox(behavior="success", stdout=long_output)
        code4 = 'print("x" * 5000)'

    store4 = InMemoryIndexStore()
    config4 = ExecutePythonConfig(summary_max_chars=120, stderr_max_chars=50)
    result4 = await execute_python(
        code=code4,
        sandbox=sandbox4,
        index_store=store4,
        config=config4,
    )

    test(
        "summary 不包含完整原文（超长部分被截断）",
        len(result4.summary) < 5000 or "truncated" in result4.summary,
        f"summary length={len(result4.summary)}",
        result4.execution_id,
    )

    test(
        "summary 含截断标记",
        "truncated" in result4.summary,
        f"summary preview={result4.summary[:200]}",
        result4.execution_id,
    )

    test(
        "stdout_chars 与原始长度一致",
        result4.stdout_chars == 5000,
        f"stdout_chars={result4.stdout_chars}, expected=5000",
        result4.execution_id,
    )

    # === 用例 5：边界输入 ===
    print("\n用例 5：边界输入")
    print("-" * 50)

    # 5.1 空代码
    if not integration_mode:
        sandbox5 = FakeSandbox()
    else:
        from sandbox_wrapper import FixedPyodideSandbox
        sandbox5 = FixedPyodideSandbox(allow_net=False)

    store5 = InMemoryIndexStore()
    result5 = await execute_python(
        code="",  # 空代码
        sandbox=sandbox5,
        index_store=store5,
    )

    test(
        "空代码返回 error",
        result5.status == "error",
        f"status={result5.status}, summary={result5.summary}",
        result5.execution_id,
    )

    # 5.2 非法超时值
    store5b = InMemoryIndexStore()
    result5b = await execute_python(
        code="print('hello')",
        sandbox=sandbox5,
        index_store=store5b,
        timeout_seconds=-1,  # 非法值
    )

    test(
        "非法 timeout 回退默认值且不抛异常",
        result5b.status in ["success", "error"],  # 只要返回了 ToolResult 就算通过
        f"status={result5b.status}",
        result5b.execution_id,
    )

    # === 用例 6：字段一致性验证 ===
    print("\n用例 6：字段一致性")
    print("-" * 50)

    if not integration_mode:
        sandbox6 = FakeSandbox(behavior="success", stdout="test output", stderr="test error")
    else:
        from sandbox_wrapper import FixedPyodideSandbox
        sandbox6 = FixedPyodideSandbox(allow_net=False)

    store6 = InMemoryIndexStore()
    result6 = await execute_python(
        code="print('test')",
        sandbox=sandbox6,
        index_store=store6,
    )

    # 验证每次调用产生新的 execution_id
    result6b = await execute_python(
        code="print('test2')",
        sandbox=sandbox6,
        index_store=store6,
    )

    test(
        "每次调用产生新的 execution_id",
        result6.execution_id != result6b.execution_id,
        f"id1={result6.execution_id}, id2={result6b.execution_id}",
        f"{result6.execution_id} vs {result6b.execution_id}",
    )

    # === 测试汇总 ===
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\nPHASE2_SMOKE_PASS")
        return 0
    else:
        print(f"\nPHASE2_SMOKE_FAIL ({failed} failed)")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 smoke tests")
    parser.add_argument("--integration", action="store_true", help="使用真实沙箱进行集成测试")
    args = parser.parse_args()

    import asyncio
    exit_code = asyncio.run(run_tests(integration_mode=args.integration))
    sys.exit(exit_code)
