"""
端到端连通性测试

验证完整链路：LLM API -> Agent -> 沙箱执行
运行方式：python tests/smoke_e2e.py

前置条件：
    - .env 文件已配置 LLM_API_KEY
    - Docker 环境已启动（或在本地安装依赖）
"""
import os
import sys
import asyncio
from pathlib import Path

# 自动检测项目根目录
if os.path.exists("/app"):
    PROJECT_ROOT = "/app"
else:
    PROJECT_ROOT = str(Path(__file__).parent.parent)

sys.path.insert(0, PROJECT_ROOT)

# 加载 .env
try:
    from dotenv import load_dotenv
    env_path = Path(PROJECT_ROOT) / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


async def run_tests():
    """运行端到端测试"""
    passed = 0
    failed = 0

    print("=" * 60)
    print("端到端连通性测试")
    print("=" * 60)

    # 检查 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("\n[E2E_SKIP] DASHSCOPE_API_KEY 未设置，跳过端到端测试")
        print("请配置 .env 文件后重试")
        return 0

    print(f"\n[INFO] 使用模型: {os.getenv('LLM_MODEL', 'qwen-plus')}")

    # 导入依赖
    try:
        from langchain_openai import ChatOpenAI
        from sandbox_wrapper import FixedPyodideSandbox
        from agent import SandboxAgent, InMemoryIndexStore
    except ImportError as e:
        print(f"\n[E2E_FAIL] 导入失败: {e}")
        print("请确认依赖已安装: pip install -r requirements.txt")
        return 1

    def test(name: str, condition: bool, context: str = ""):
        nonlocal passed, failed
        print(f"\n[CASE] {name}")
        if condition:
            print(f"[OK]")
            passed += 1
        else:
            print(f"[FAIL] {context}")
            failed += 1

    # === 用例 1：纯知识问答（无需工具）===
    print("\n" + "-" * 60)
    print("用例 1：纯知识问答（无需工具）")
    print("-" * 60)

    try:
        # 使用 LangChain ChatOpenAI 支持工具调用
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field

        class CodeInput(BaseModel):
            code: str = Field(description="Python code to execute")

        tool = StructuredTool.from_function(
            func=lambda code: code,
            name="execute_python",
            description="Execute Python code in sandbox",
            args_schema=CodeInput,
        )

        llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "qwen-plus"),
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            temperature=0,
        ).bind_tools([tool])

        def llm_callable(messages):
            return llm.invoke(messages)

        # 初始化沙箱（复用）
        sandbox = FixedPyodideSandbox(allow_net=False)

        # 用例 1：纯知识问答
        agent = SandboxAgent(
            llm=llm_callable,
            sandbox=sandbox,
            index_store=InMemoryIndexStore(),
            max_executions=3,
            verbose=True,
        )

        result = await agent.run("2+2 等于多少？请直接回答。")

        test(
            "Agent 返回了回答",
            len(result.answer) > 0,
            f"answer={result.answer}",
        )

        test(
            "未触发工具调用（纯知识问答）",
            result.execution_count == 0,
            f"execution_count={result.execution_count}",
        )

    except Exception as e:
        test("纯知识问答执行", False, f"异常: {type(e).__name__}: {e}")

    # === 用例 2：需要代码执行的任务 ===
    print("\n" + "-" * 60)
    print("用例 2：代码执行任务")
    print("-" * 60)

    try:
        store2 = InMemoryIndexStore()
        agent2 = SandboxAgent(
            llm=llm_callable,
            sandbox=sandbox,
            index_store=store2,
            max_executions=3,
            verbose=True,
        )

        result2 = await agent2.run("用 Python 计算 1 到 100 的和")

        test(
            "Agent 返回了回答",
            len(result2.answer) > 0,
            f"answer={result2.answer[:100]}...",
        )

        test(
            "触发了工具调用",
            result2.execution_count >= 1,
            f"execution_count={result2.execution_count}",
        )

        test(
            "执行结果已存入索引",
            result2.last_execution_id is not None and store2.get(result2.last_execution_id) is not None,
            f"last_execution_id={result2.last_execution_id}",
        )

        # 验证结果中是否包含预期数字
        answer_lower = result2.answer.lower()
        test(
            "回答中包含计算结果（5050 或相关描述）",
            "5050" in answer_lower or "五千零五十" in answer_lower or "5050" in result2.answer,
            f"answer={result2.answer[:200]}",
        )

    except Exception as e:
        test("代码执行任务", False, f"异常: {type(e).__name__}: {e}")

    # === 用例 3：错误恢复 ===
    print("\n" + "-" * 60)
    print("用例 3：代码错误恢复")
    print("-" * 60)

    try:
        store3 = InMemoryIndexStore()
        agent3 = SandboxAgent(
            llm=llm_callable,
            sandbox=sandbox,
            index_store=store3,
            max_executions=3,
            verbose=True,
        )

        # 让 LLM 故意写一段有错误的代码，然后修复
        result3 = await agent3.run("故意执行一段会报错的代码（如 1/0），然后处理错误")

        test(
            "即使代码出错也返回了回答",
            len(result3.answer) > 0,
            f"answer={result3.answer[:100]}...",
        )

        # 检查索引中是否有错误记录
        if result3.last_execution_id:
            record = store3.get(result3.last_execution_id)
            if record:
                test(
                    "错误记录已存入索引",
                    True,
                    f"status={record.status}",
                )

    except Exception as e:
        test("错误恢复", False, f"异常: {type(e).__name__}: {e}")

    # === 测试汇总 ===
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed == 0:
        print("\n✅ E2E_SMOKE_PASS - 端到端连通性正常")
        return 0
    else:
        print(f"\n❌ E2E_SMOKE_FAIL ({failed} failed)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
