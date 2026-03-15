"""
Phase 1 冒烟测试

验证基础数据结构与索引存储层可用性
运行方式：python tests/smoke_phase1.py
"""
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, "d:/Code/my-sandbox-demo")

from agent import InMemoryIndexStore, ExecutionRecord


def run_tests():
    """运行所有冒烟测试用例"""
    passed = 0
    failed = 0

    def test(name, condition, context=""):
        nonlocal passed, failed
        print(f"[CASE] {name}")
        if condition:
            print(f"[OK]")
            passed += 1
        else:
            print(f"[FAIL] {context}")
            failed += 1

    # === 用例 1：基础写入与读取 ===
    print("\n" + "=" * 50)
    print("用例 1：基础写入与读取")
    print("=" * 50)

    store = InMemoryIndexStore()
    execution_id = store.save({
        "status": "success",
        "stdout": "hello world",
        "stderr": "",
        "result": 42,
        "execution_time": 1.5,
    })

    test(
        "save 返回非空 execution_id",
        execution_id and len(execution_id) > 0,
        f"execution_id={execution_id}"
    )

    record = store.get(execution_id)
    test(
        "get 返回记录且 ID 一致",
        record is not None and record.execution_id == execution_id,
        f"record={record}"
    )

    test(
        "记录字段完整",
        record and record.stdout == "hello world" and record.status == "success",
        f"stdout={record.stdout if record else None}, status={record.status if record else None}"
    )

    # === 用例 2：最近记录顺序 ===
    print("\n" + "=" * 50)
    print("用例 2：最近记录顺序")
    print("=" * 50)

    store2 = InMemoryIndexStore()
    id_a = store2.save({"status": "success", "stdout": "A"})
    id_b = store2.save({"status": "success", "stdout": "B"})
    id_c = store2.save({"status": "success", "stdout": "C"})

    latest = store2.latest(2)
    test(
        "latest(2) 返回 2 条记录",
        len(latest) == 2,
        f"len={len(latest)}"
    )

    test(
        "顺序正确 [C, B]",
        len(latest) == 2 and latest[0].stdout == "C" and latest[1].stdout == "B",
        f"order={[r.stdout for r in latest]}"
    )

    # === 用例 3：边界输入 ===
    print("\n" + "=" * 50)
    print("用例 3：边界输入")
    print("=" * 50)

    store3 = InMemoryIndexStore()
    store3.save({"status": "success"})  # 先存一条确保有数据

    test(
        "latest(0) 返回空列表",
        store3.latest(0) == [],
        f"result={store3.latest(0)}"
    )

    test(
        "latest(-5) 返回空列表",
        store3.latest(-5) == [],
        f"result={store3.latest(-5)}"
    )

    test(
        "get(不存在ID) 返回 None",
        store3.get("not-exist-12345") is None,
        f"result={store3.get('not-exist-12345')}"
    )

    # === 用例 4：字段兜底 ===
    print("\n" + "=" * 50)
    print("用例 4：字段兜底")
    print("=" * 50)

    store4 = InMemoryIndexStore()
    min_id = store4.save({"status": "error"})  # 最小记录

    min_record = store4.get(min_id)
    test(
        "stdout 存在默认值",
        min_record and min_record.stdout == "",
        f"stdout={min_record.stdout if min_record else None}"
    )

    test(
        "stderr 存在默认值",
        min_record and min_record.stderr == "",
        f"stderr={min_record.stderr if min_record else None}"
    )

    test(
        "result 存在默认值",
        min_record and min_record.result is None,
        f"result={min_record.result if min_record else None}"
    )

    test(
        "created_at 存在且可解析",
        min_record and _is_valid_iso_datetime(min_record.created_at),
        f"created_at={min_record.created_at if min_record else None}"
    )

    # === 用例 5：ExecutionRecord 数据结构 ===
    print("\n" + "=" * 50)
    print("用例 5：ExecutionRecord 数据结构")
    print("=" * 50)

    record = ExecutionRecord(
        execution_id="test-123",
        status="success",
        stdout="output",
        stderr="error",
        result={"key": "value"},
        execution_time=2.5,
    )

    test(
        "to_dict 转换正确",
        record.to_dict()["execution_id"] == "test-123" and record.to_dict()["status"] == "success",
        f"dict={record.to_dict()}"
    )

    record_dict = record.to_dict()
    restored = ExecutionRecord.from_dict(record_dict)
    test(
        "from_dict 恢复正确",
        restored.execution_id == "test-123" and restored.stdout == "output",
        f"restored={restored}"
    )

    # === 测试汇总 ===
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\nPHASE1_SMOKE_PASS")
        return 0
    else:
        print(f"\nPHASE1_SMOKE_FAIL ({failed} failed)")
        return 1


def _is_valid_iso_datetime(s: str) -> bool:
    """检查字符串是否为有效的ISO8601时间格式"""
    try:
        datetime.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
