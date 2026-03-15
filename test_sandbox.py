"""
沙箱环境验证测试
重点测试：执行延迟、stdout/stderr 捕获完整性、异常隔离
"""
import asyncio
import time
from langchain_sandbox import PyodideSandbox


async def test_execution_latency():
    """测试执行延迟"""
    print("=" * 60)
    print("【测试1】执行延迟测试")
    print("=" * 60)

    # 冷启动测试
    print("\n▶ 冷启动测试（首次创建沙箱）...")
    start = time.perf_counter()
    sandbox = PyodideSandbox(allow_net=True)
    cold_start_time = time.perf_counter() - start
    print(f"  沙箱创建耗时: {cold_start_time:.2f}s")

    # 首次执行
    code = "print('hello')"
    start = time.perf_counter()
    result = await sandbox.execute(code)
    first_exec_time = time.perf_counter() - start
    print(f"  首次执行耗时: {first_exec_time:.2f}s")
    print(f"  冷启动总耗时: {cold_start_time + first_exec_time:.2f}s")

    # 热执行测试
    print("\n▶ 热执行测试（复用同一沙箱）...")
    exec_times = []
    for i in range(5):
        code = f"print('run {i+1}')"
        start = time.perf_counter()
        result = await sandbox.execute(code)
        exec_time = time.perf_counter() - start
        exec_times.append(exec_time)
        print(f"  第{i+1}次执行: {exec_time:.3f}s")

    avg_time = sum(exec_times) / len(exec_times)
    print(f"  平均执行耗时: {avg_time:.3f}s")
    print(f"  冷启动/热执行比率: {(cold_start_time + first_exec_time) / avg_time:.1f}x")

    return sandbox


async def test_output_capture(sandbox):
    """测试 stdout/stderr 捕获完整性"""
    print("\n" + "=" * 60)
    print("【测试2】stdout/stderr 捕获完整性测试")
    print("=" * 60)

    # 大量输出测试
    print("\n▶ 大量输出测试（1000行）...")
    code = """
for i in range(1000):
    print(f"Line {i:04d}: " + "x" * 50)
"""
    result = await sandbox.execute(code)
    lines = result.stdout.strip().split('\n')
    print(f"  预期行数: 1000")
    print(f"  实际捕获: {len(lines)} 行")
    print(f"  状态: {'✓ 通过' if len(lines) == 1000 else '✗ 失败'}")

    # 多流混合测试
    print("\n▶ stdout/stderr 混合输出测试...")
    code = """
import sys
print("stdout-1")
print("stderr-1", file=sys.stderr)
print("stdout-2")
print("stderr-2", file=sys.stderr)
print("stdout-3")
"""
    result = await sandbox.execute(code)
    print(f"  stdout: {repr(result.stdout)}")
    print(f"  stderr: {repr(result.stderr)}")

    # 特殊字符测试
    print("\n▶ 特殊字符测试...")
    code = r"""
print("Unicode: 你好世界 🌍 émojis")
print("Special: \n\t\r\\'\"")
print("Empty line below")
print()
print("After empty")
"""
    result = await sandbox.execute(code)
    print(f"  输出:\n{result.stdout}")

    # 长行测试
    print("\n▶ 长行测试（10000字符）...")
    code = """
print("x" * 10000)
"""
    result = await sandbox.execute(code)
    output_len = len(result.stdout.strip())
    print(f"  预期长度: 10000")
    print(f"  实际长度: {output_len}")
    print(f"  状态: {'✓ 通过' if output_len == 10000 else '✗ 失败'}")


async def test_exception_isolation(sandbox):
    """测试异常隔离"""
    print("\n" + "=" * 60)
    print("【测试3】异常隔离测试")
    print("=" * 60)

    # 语法错误
    print("\n▶ 语法错误测试...")
    code = """
if True
    print("missing colon")
"""
    result = await sandbox.execute(code)
    print(f"  stderr: {result.stderr[:200] if result.stderr else 'None'}...")
    print(f"  状态: {'✓ 异常已捕获' if result.stderr else '✗ 未捕获'}")

    # 运行时异常
    print("\n▶ 运行时异常测试...")
    test_cases = [
        ("ZeroDivisionError", "1/0"),
        ("NameError", "print(undefined_var)"),
        ("TypeError", "'string' + 123"),
        ("IndexError", "[1,2,3][10]"),
    ]
    for name, code in test_cases:
        result = await sandbox.execute(code)
        captured = name in result.stderr if result.stderr else False
        print(f"  {name}: {'✓' if captured else '✗'}")

    # 异常后恢复测试
    print("\n▶ 异常后恢复测试...")
    await sandbox.execute("1/0")  # 制造异常
    result = await sandbox.execute("print('after exception')")
    recovered = "after exception" in result.stdout if result.stdout else False
    print(f"  异常后是否能继续执行: {'✓ 是' if recovered else '✗ 否'}")

    # 内存测试
    print("\n▶ 内存分配测试...")
    code = """
try:
    big_list = [0] * (10**7)  # 约 80MB
    print(f"Created list with {len(big_list)} items")
except MemoryError as e:
    print(f"MemoryError: {e}")
"""
    result = await sandbox.execute(code)
    print(f"  输出: {result.stdout.strip() if result.stdout else 'None'}")


async def test_computation(sandbox):
    """测试纯计算场景（CPU密集型）"""
    print("\n" + "=" * 60)
    print("【测试4】纯计算场景测试（斐波那契数列）")
    print("=" * 60)

    # 测试1: 斐波那契计算（迭代方式）
    print("\n▶ 斐波那契数列计算（迭代，n=35）...")
    code = """
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

result = fibonacci(35)
print(f"F(35) = {result}")
result
"""
    start = time.perf_counter()
    result = await sandbox.execute(code)
    exec_time = time.perf_counter() - start

    print(f"  执行时间: {exec_time:.3f}s")
    print(f"  输出: {result.stdout.strip() if result.stdout else 'None'}")
    print(f"  返回值: {result.result}")
    print(f"  状态: {'✓ 通过' if result.result == 9227465 else '✗ 结果错误'}")

    # 测试2: 大数斐波那契（测试大整数处理）
    print("\n▶ 大数斐波那契计算（n=100）...")
    code = """
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

result = fibonacci(100)
print(f"F(100) = {result}")
print(f"位数: {len(str(result))}")
result
"""
    start = time.perf_counter()
    result = await sandbox.execute(code)
    exec_time = time.perf_counter() - start

    print(f"  执行时间: {exec_time:.3f}s")
    print(f"  位数: {result.stdout.split('位数: ')[-1].strip() if result.stdout and '位数:' in result.stdout else 'Unknown'}")

    # 测试3: 递归深度测试（斐波那契递归）
    print("\n▶ 递归斐波那契（n=20，测试递归深度）...")
    code = """
def fib_recursive(n):
    if n <= 1:
        return n
    return fib_recursive(n - 1) + fib_recursive(n - 2)

result = fib_recursive(20)
print(f"F(20) = {result}")
result
"""
    start = time.perf_counter()
    result = await sandbox.execute(code)
    exec_time = time.perf_counter() - start

    print(f"  执行时间: {exec_time:.3f}s")
    print(f"  输出: {result.stdout.strip() if result.stdout else 'None'}")
    print(f"  状态: {'✓ 通过' if result.result == 6765 else '✗ 结果错误'}")


async def main():
    print("\n" + "=" * 60)
    print("LangChain Sandbox 环境验证测试")
    print("=" * 60)

    # 测试1: 执行延迟
    sandbox = await test_execution_latency()

    # 测试2: 输出捕获
    await test_output_capture(sandbox)

    # 测试3: 异常隔离
    await test_exception_isolation(sandbox)

    # 测试4: 纯计算场景
    await test_computation(sandbox)

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
