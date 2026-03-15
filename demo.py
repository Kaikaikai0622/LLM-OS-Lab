import asyncio
from langchain_sandbox import PyodideSandbox

async def main():
    print("正在启动沙箱（首次启动需要几秒）...")
    
    sandbox = PyodideSandbox(allow_net=True)
    
    code = """
import sys
print(f"Python 版本: {sys.version}")
print("Hello from Sandbox!")

# 测试数学计算
result = sum(range(1, 101))
print(f"1+2+...+100 = {result}")
"""
    
    result = await sandbox.execute(code)
    print("\n执行结果：")
    print(result.stdout)
    
    if result.stderr:
        print("错误信息：", result.stderr)

asyncio.run(main())