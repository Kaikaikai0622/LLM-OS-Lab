"""
Phase 4 冒烟测试

验证 CLI 入口、配置校验和参数覆盖
运行方式：python tests/smoke_phase4.py
"""
import os
import sys
import subprocess
from pathlib import Path

# 自动检测项目根目录（支持本地和 Docker 环境）
if os.path.exists("/app"):
    # Docker 环境
    PROJECT_ROOT = "/app"
else:
    # 本地环境
    PROJECT_ROOT = str(Path(__file__).parent.parent)

sys.path.insert(0, PROJECT_ROOT)


def run_agent(args: list, env: dict = None) -> tuple[int, str, str]:
    """
    运行 agent 命令

    Returns:
        (exit_code, stdout, stderr)
    """
    cmd = [sys.executable, "-m", "agent"] + args
    test_env = os.environ.copy()
    if env:
        test_env.update(env)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=test_env,
        cwd=PROJECT_ROOT,
    )
    return result.returncode, result.stdout, result.stderr


def run_tests():
    """运行所有冒烟测试用例"""
    passed = 0
    failed = 0

    print("=" * 50)
    print("Phase 4 冒烟测试")
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

    # === 用例 1：空 query ===
    print("\n用例 1：空 query")
    print("-" * 50)

    exit_code, stdout, stderr = run_agent([])
    combined = stdout + stderr

    test(
        "退出码非 0",
        exit_code != 0,
        f"exit_code={exit_code}",
    )

    test(
        "输出包含 usage 或 CONFIG_ERROR",
        "usage" in combined.lower() or "CONFIG_ERROR" in combined or "error" in combined.lower(),
        f"output={combined[:200]}",
    )

    # === 用例 2：缺少 API_KEY ===
    print("\n用例 2：缺少 API_KEY")
    print("-" * 50)

    # 清空 API_KEY
    env_no_key = {"DASHSCOPE_API_KEY": ""}
    exit_code, stdout, stderr = run_agent(["测试问题"], env=env_no_key)
    combined = stdout + stderr

    test(
        "退出码非 0",
        exit_code != 0,
        f"exit_code={exit_code}",
    )

    test(
        "输出包含 [CONFIG_ERROR]",
        "[CONFIG_ERROR]" in combined or "DASHSCOPE_API_KEY" in combined,
        f"output={combined[:200]}",
    )

    # === 用例 3：非法数值配置 ===
    print("\n用例 3：非法数值配置")
    print("-" * 50)

    env_bad_config = {
        "DASHSCOPE_API_KEY": "fake-key",
        "AGENT_MAX_EXECUTIONS": "0",
    }
    exit_code, stdout, stderr = run_agent(["测试问题"], env=env_bad_config)
    combined = stdout + stderr

    test(
        "退出码非 0",
        exit_code != 0,
        f"exit_code={exit_code}",
    )

    test(
        "输出包含 AGENT_MAX_EXECUTIONS 或必须是正整数",
        "AGENT_MAX_EXECUTIONS" in combined or "正整数" in combined or "必须" in combined,
        f"output={combined[:200]}",
    )

    # === 用例 4：--help 正常显示 ===
    print("\n用例 4：--help 正常显示")
    print("-" * 50)

    exit_code, stdout, stderr = run_agent(["--help"])
    combined = stdout + stderr

    test(
        "退出码为 0",
        exit_code == 0,
        f"exit_code={exit_code}",
    )

    test(
        "输出包含 usage 或帮助信息",
        "usage" in combined.lower() or "sandbox" in combined.lower() or "help" in combined.lower(),
        f"output={combined[:200]}",
    )

    # === 用例 5：requirements.txt 存在 ===
    print("\n用例 5：requirements.txt 存在")
    print("-" * 50)

    req_file = Path(PROJECT_ROOT) / "requirements.txt"
    test(
        "requirements.txt 存在",
        req_file.exists(),
        f"文件不存在: {req_file}",
    )

    if req_file.exists():
        content = req_file.read_text()
        test(
            "包含 langchain 依赖",
            "langchain" in content,
            f"content={content[:100]}",
        )

    # === 用例 6：.env.example 存在 ===
    print("\n用例 6：.env.example 存在")
    print("-" * 50)

    env_example = Path(PROJECT_ROOT) / ".env.example"
    test(
        ".env.example 存在",
        env_example.exists(),
        f"文件不存在: {env_example}",
    )

    if env_example.exists():
        content = env_example.read_text()
        test(
            "包含 DASHSCOPE_API_KEY 字段",
            "DASHSCOPE_API_KEY" in content,
            f"content={content[:100]}",
        )
        test(
            "包含 AGENT_MAX_EXECUTIONS 字段",
            "AGENT_MAX_EXECUTIONS" in content,
            f"content={content[:100]}",
        )

    # === 用例 7：agent/__main__.py 存在 ===
    print("\n用例 7：agent/__main__.py 存在")
    print("-" * 50)

    main_file = Path(PROJECT_ROOT) / "agent" / "__main__.py"
    test(
        "agent/__main__.py 存在",
        main_file.exists(),
        f"文件不存在: {main_file}",
    )

    if main_file.exists():
        content = main_file.read_text()
        test(
            "包含 ConfigError 定义",
            "ConfigError" in content,
            f"content={content[:100]}",
        )
        test(
            "包含 validate_config 函数",
            "validate_config" in content,
            f"content={content[:100]}",
        )

    # === 测试汇总 ===
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\nPHASE4_SMOKE_PASS")
        return 0
    else:
        print(f"\nPHASE4_SMOKE_FAIL ({failed} failed)")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
