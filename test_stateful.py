"""
Stateful 模式对比测试
对比 stateful=True 和 stateful=False 的性能差异
"""
import asyncio
import time
from langchain_sandbox import PyodideSandbox


async def test_stateless_mode():
    """测试无状态模式（每次新建沙箱）"""
    print("=" * 60)
    print("【测试1】Stateless 模式（stateful=False）")
    print("=" * 60)

    execution_times = []

    for i in range(3):
        sandbox = PyodideSandbox(allow_net=True)

        code = f"""
result = {i} * 10
print(f"Result: {{result}}")
result
"""
        start = time.perf_counter()
        result = await sandbox.execute(code)
        exec_time = time.perf_counter() - start

        execution_times.append(exec_time)
        print(f"\n第{i+1}次执行:")
        print(f"  耗时: {exec_time:.2f}s")
        print(f"  输出: {result.stdout}")
        print(f"  返回值: {result.result}")

    avg_time = sum(execution_times) / len(execution_times)
    print(f"\n平均执行时间: {avg_time:.2f}s")

    return execution_times


async def test_stateful_mode():
    """测试有状态模式（复用 session）"""
    print("\n" + "=" * 60)
    print("【测试2】Stateful 模式（stateful=True）")
    print("=" * 60)

    # 创建有状态沙箱
    sandbox = PyodideSandbox(allow_net=True, stateful=True)

    execution_times = []
    session_bytes = None
    session_metadata = None

    for i in range(3):
        code = f"""
# 累加计算，验证状态保持
if 'counter' not in locals():
    counter = 0
counter += {i + 1}
print(f"Iteration {i+1}, Counter: {{counter}}")
counter
"""
        start = time.perf_counter()
        result = await sandbox.execute(
            code,
            session_bytes=session_bytes,
            session_metadata=session_metadata
        )
        exec_time = time.perf_counter() - start

        execution_times.append(exec_time)

        # 保存 session 用于下次执行
        session_bytes = result.session_bytes
        session_metadata = result.session_metadata

        print(f"\n第{i+1}次执行:")
        print(f"  耗时: {exec_time:.2f}s")
        print(f"  输出: {result.stdout}")
        print(f"  返回值: {result.result}")
        print(f"  Session 大小: {len(session_bytes) if session_bytes else 0} bytes")

    avg_time = sum(execution_times) / len(execution_times)
    print(f"\n平均执行时间: {avg_time:.2f}s")

    return execution_times


async def test_variable_persistence():
    """测试变量持久化"""
    print("\n" + "=" * 60)
    print("【测试3】变量持久化测试")
    print("=" * 60)

    sandbox = PyodideSandbox(allow_net=True, stateful=True)
    session_bytes = None
    session_metadata = None

    # 第一次：定义变量
    print("\n▶ 第1次：定义变量")
    result = await sandbox.execute("""
x = 42
y = [1, 2, 3]
z = {'name': 'test'}
print(f"Defined: x={x}, y={y}, z={z}")
""", session_bytes=session_bytes, session_metadata=session_metadata)
    session_bytes = result.session_bytes
    session_metadata = result.session_metadata
    print(f"  输出: {result.stdout}")

    # 第二次：使用之前定义的变量
    print("\n▶ 第2次：读取变量")
    result = await sandbox.execute("""
print(f"x = {x}")
print(f"y = {y}")
print(f"z = {z}")
x += 10
y.append(4)
z['new_key'] = 'new_value'
print(f"Modified: x={x}, y={y}, z={z}")
""", session_bytes=session_bytes, session_metadata=session_metadata)
    session_bytes = result.session_bytes
    session_metadata = result.session_metadata
    print(f"  输出: {result.stdout}")

    # 第三次：验证修改已保存
    print("\n▶ 第3次：验证修改")
    result = await sandbox.execute("""
print(f"Final: x={x}, y={y}, z={z}")
""", session_bytes=session_bytes, session_metadata=session_metadata)
    print(f"  输出: {result.stdout}")


async def main():
    print("\n" + "=" * 60)
    print("Stateful 模式对比测试")
    print("=" * 60)

    # 测试1: Stateless 模式
    stateless_times = await test_stateless_mode()

    # 测试2: Stateful 模式
    stateful_times = await test_stateful_mode()

    # 测试3: 变量持久化
    await test_variable_persistence()

    # 汇总对比
    print("\n" + "=" * 60)
    print("【汇总对比】")
    print("=" * 60)
    print(f"Stateless 平均: {sum(stateless_times)/len(stateless_times):.2f}s")
    print(f"Stateful 平均:   {sum(stateful_times)/len(stateful_times):.2f}s")
    if len(stateful_times) >= 2 and len(stateless_times) >= 2:
        speedup = stateless_times[0] / stateful_times[1] if stateful_times[1] > 0 else 0
        print(f"\n第1次执行（冷启动）:")
        print(f"  Stateless: {stateless_times[0]:.2f}s")
        print(f"  Stateful:  {stateful_times[0]:.2f}s")
        print(f"\n第2次执行（热执行）:")
        print(f"  Stateless: {stateless_times[1]:.2f}s")
        print(f"  Stateful:  {stateful_times[1]:.2f}s")
        print(f"\n注意: Stateful 模式在后续执行中应该更快（如果 session 复用生效）")


if __name__ == "__main__":
    asyncio.run(main())
