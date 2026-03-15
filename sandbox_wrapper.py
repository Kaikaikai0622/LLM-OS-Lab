"""
PyodideSandbox 包装器
提供换行符修复和其他增强功能
"""
import asyncio
import re
from dataclasses import dataclass
from typing import Optional, Any
from langchain_sandbox import PyodideSandbox
from langchain_sandbox.pyodide import CodeExecutionResult


@dataclass
class FixedExecutionResult:
    """修复后的执行结果"""
    result: Any = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    status: str = "success"
    execution_time: float = 0.0
    session_metadata: Optional[dict] = None
    session_bytes: Optional[bytes] = None
    raw_result: Optional[CodeExecutionResult] = None  # 原始结果


class FixedPyodideSandbox:
    """
    修复了换行符问题的 PyodideSandbox 包装器

    主要修复：
    1. 恢复 stdout/stderr 中丢失的换行符
    2. 提供更友好的结果访问方式

    使用方法：
        sandbox = FixedPyodideSandbox(allow_net=True)
        result = await sandbox.execute("print('line1')\\nprint('line2')")
        print(result.stdout)  # 现在会正确显示换行
    """

    def __init__(self, *, allow_net: bool = False, stateful: bool = False, **kwargs):
        self._sandbox = PyodideSandbox(allow_net=allow_net, stateful=stateful, **kwargs)
        self._stateful = stateful
        self._session_bytes: Optional[bytes] = None
        self._session_metadata: Optional[dict] = None

    async def execute(
        self,
        code: str,
        *,
        timeout_seconds: Optional[float] = None,
        memory_limit_mb: Optional[int] = None
    ) -> FixedExecutionResult:
        """
        执行 Python 代码，修复换行符问题

        Args:
            code: 要执行的 Python 代码
            timeout_seconds: 超时时间
            memory_limit_mb: 内存限制

        Returns:
            FixedExecutionResult: 修复后的执行结果
        """
        # 如果是 stateful 模式，传递 session
        kwargs = {}
        if self._stateful:
            kwargs['session_bytes'] = self._session_bytes
            kwargs['session_metadata'] = self._session_metadata

        # 执行原始代码
        result = await self._sandbox.execute(
            code,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            **kwargs
        )

        # 修复换行符
        fixed_stdout = self._fix_newlines(result.stdout, code) if result.stdout else None
        fixed_stderr = self._fix_newlines(result.stderr, code) if result.stderr else None

        # 保存 session（stateful 模式）
        if self._stateful:
            self._session_bytes = result.session_bytes
            self._session_metadata = result.session_metadata

        return FixedExecutionResult(
            result=result.result,
            stdout=fixed_stdout,
            stderr=fixed_stderr,
            status=result.status,
            execution_time=result.execution_time,
            session_metadata=result.session_metadata,
            session_bytes=result.session_bytes,
            raw_result=result
        )

    def _fix_newlines(self, output: str, original_code: str) -> str:
        """
        尝试恢复输出中的换行符

        策略：
        1. 如果输出中已经有换行符，不做处理
        2. 识别输出中的重复模式（如 "Iteration 0", "Iteration 1"）
        3. 根据模式边界智能插入换行符
        """
        if not output:
            return output

        # 如果输出已经包含换行符，不做处理
        if '\n' in output:
            return output

        # 计算原始代码中应该产生的换行数
        print_count = self._count_print_statements(original_code)

        if print_count <= 1:
            return output

        # 首先尝试通过检测重复模式来分割
        lines = self._split_by_pattern(output, print_count)
        if lines:
            return '\n'.join(lines)

        # 如果模式检测失败，尝试均匀分割
        output_len = len(output)
        if output_len >= print_count:
            chars_per_line = output_len // print_count
            lines = []
            for i in range(print_count):
                start = i * chars_per_line
                end = start + chars_per_line if i < print_count - 1 else output_len
                line = output[start:end]
                lines.append(line)
            return '\n'.join(lines)

        return output

    def _split_by_pattern(self, output: str, expected_lines: int) -> list[str] | None:
        """
        通过检测重复模式来分割输出

        例如 "Iteration 0Iteration 1Iteration 2" -> ["Iteration 0", "Iteration 1", "Iteration 2"]
        """
        if len(output) < expected_lines * 2:
            return None

        lines = []
        current_pos = 0
        remaining_lines = expected_lines
        remaining_chars = len(output)

        while remaining_lines > 1 and current_pos < len(output):
            # 动态计算平均长度（根据剩余内容）
            avg_line_len = remaining_chars // remaining_lines

            # 在估计位置附近搜索
            search_start = current_pos + max(1, avg_line_len - 15)
            search_end = min(len(output), current_pos + avg_line_len + 15)

            split_pos = self._find_split_position(output, search_start, search_end)

            if split_pos > current_pos:
                line = output[current_pos:split_pos]
                lines.append(line)
                remaining_chars -= len(line)
                remaining_lines -= 1
                current_pos = split_pos
            else:
                return None

        # 添加最后一行
        if current_pos < len(output):
            lines.append(output[current_pos:])

        return lines if len(lines) == expected_lines else None

    def _find_split_position(self, output: str, start: int, end: int) -> int:
        """
        寻找合适的分割位置

        启发式规则：
        1. 数字后跟字母（如 "0I" 在 "Iteration 0Iteration 1"）
        2. 大写字母后跟空格或常见模式开始
        3. 空格位置（前后都有字母）
        """
        if start >= len(output):
            return len(output)

        end = min(end, len(output))

        # 策略1：找数字后跟字母的位置（最常见的情况）
        for i in range(start, end):
            if i + 1 < len(output):
                if output[i].isdigit() and output[i + 1].isalpha():
                    return i + 1

        # 策略2：找空格后紧跟大写字母（如 " Start"）
        for i in range(start, end - 1):
            if output[i] == ' ' and output[i + 1].isupper():
                return i + 1

        # 策略3：找小写转大写的边界（如 "StartI" 中的 "tI"）
        for i in range(start, end):
            if i + 1 < len(output):
                if output[i].islower() and output[i + 1].isupper():
                    return i + 1

        # 策略4：尝试找单词边界（两个字母之间，前一个和后一个是非字母）
        for i in range(start + 1, end):
            if i + 1 < len(output):
                # 找 "字母+非字母+字母" 的模式，暗示可能的边界
                if output[i-1].isalpha() and not output[i].isalpha() and output[i+1].isalpha():
                    # 检查这是否是合理的分割点（非字母应该是分隔符）
                    if output[i] in ' :;,.-_':
                        return i + 1

        # 如果没有找到，返回中间位置
        return (start + end) // 2

    def _count_print_statements(self, code: str) -> int:
        """统计代码中的 print 语句执行次数（考虑循环）"""
        # 移除注释和字符串
        code_clean = re.sub(r'["\'][^"\']*["\']', '""', code)
        code_no_comments = re.sub(r'#.*$', '', code_clean, flags=re.MULTILINE)

        # 检查是否有 end='' 的情况
        end_empty_pattern = r'\bprint\s*\([^)]*end\s*=\s*["\']["\']'
        code_no_end_empty = re.sub(end_empty_pattern, 'print()', code_no_comments)

        # 检测循环
        loop_pattern = r'for\s+\w+\s+in\s+range\s*\(\s*(\d+)\s*\):\s*\n\s*(\S.+)'
        loop_matches = re.findall(loop_pattern, code_no_end_empty)

        total_count = 0

        if loop_matches:
            for loop_count, loop_body in loop_matches:
                # 统计循环体内的 print 数量
                body_prints = len(re.findall(r'\bprint\s*\(', loop_body))
                total_count += int(loop_count) * body_prints

        # 统计所有 print（包括循环内外的）
        all_prints = len(re.findall(r'\bprint\s*\(', code_no_end_empty))

        # 如果有循环，我们需要重新计算
        if loop_matches:
            # 简单估计：循环体外的 print + 循环体内的 print * 次数
            # 这里简化处理，假设循环体在缩进块中
            lines = code_no_end_empty.split('\n')
            outside_prints = 0
            in_loop = False
            loop_indent = 0

            for i, line in enumerate(lines):
                if re.match(r'^\s*for\s+\w+\s+in\s+range', line):
                    in_loop = True
                    loop_indent = len(line) - len(line.lstrip())
                    # 提取循环次数
                    match = re.search(r'range\s*\(\s*(\d+)\s*\)', line)
                    if match:
                        current_loop_count = int(match.group(1))
                    continue

                if in_loop:
                    if line.strip():
                        current_indent = len(line) - len(line.lstrip())
                        if current_indent <= loop_indent:
                            in_loop = False
                        else:
                            # 在循环体内
                            if re.search(r'\bprint\s*\(', line):
                                outside_prints += current_loop_count
                            continue

                if not in_loop:
                    if re.search(r'\bprint\s*\(', line):
                        outside_prints += 1

            return max(1, outside_prints)

        return max(1, all_prints)

    @property
    def session_bytes(self) -> Optional[bytes]:
        """获取当前 session bytes（stateful 模式）"""
        return self._session_bytes

    @property
    def session_metadata(self) -> Optional[dict]:
        """获取当前 session 元数据（stateful 模式）"""
        return self._session_metadata


# 便捷函数（使用 FixedPyodideSandbox）
async def run_code(
    code: str,
    *,
    allow_net: bool = False,
    stateful: bool = False,
    fix_newlines: bool = True  # deprecated, always uses FixedPyodideSandbox
) -> FixedExecutionResult:
    """
    便捷函数：快速执行 Python 代码

    Args:
        code: Python 代码
        allow_net: 是否允许网络访问
        stateful: 是否使用有状态模式
        fix_newlines: 是否修复换行符

    Returns:
        FixedExecutionResult: 执行结果

    Example:
        result = await run_code("print('hello')\\nprint('world')")
        print(result.stdout)  # 正确显示两行
    """
    sandbox = FixedPyodideSandbox(allow_net=allow_net, stateful=stateful)
    return await sandbox.execute(code)


# 测试代码
async def test_fix():
    """测试换行符修复功能"""
    print("=" * 60)
    print("换行符修复测试")
    print("=" * 60)

    # 测试1: 基本修复
    print("\n【测试1】基本换行符修复")
    sandbox = FixedPyodideSandbox(allow_net=True)
    result = await sandbox.execute("""
print("Line 1")
print("Line 2")
print("Line 3")
""")
    print(f"修复前（原始）: {repr(result.raw_result.stdout)}")
    print(f"修复后: {repr(result.stdout)}")
    print(f"显示效果:\n{result.stdout}")

    # 测试2: 循环中的 print
    print("\n【测试2】循环中的 print 修复")
    code = """
for i in range(5):
    print(f"Iteration {i}")
"""
    result = await sandbox.execute(code)
    print(f"修复前（原始）: {repr(result.raw_result.stdout)}")
    print(f"修复后: {repr(result.stdout)}")
    print(f"显示效果:\n{result.stdout}")

    # 测试3: 更复杂的循环输出
    print("\n【测试3】复杂循环输出修复")
    code = """
for i in range(3):
    print(f"Step {i+1}: processing item {i}")
"""
    result = await sandbox.execute(code)
    print(f"修复前（原始）: {repr(result.raw_result.stdout)}")
    print(f"修复后: {repr(result.stdout)}")
    print(f"显示效果:\n{result.stdout}")

    # 测试4: 混合输出（顺序 + 循环）
    print("\n【测试4】混合输出（顺序 + 循环）- 修复有局限")
    code = """
print("Start")
for i in range(3):
    print(f"Item {i}")
print("End")
"""
    result = await sandbox.execute(code)
    print(f"修复前（原始）: {repr(result.raw_result.stdout)}")
    print(f"修复后: {repr(result.stdout)}")
    print(f"显示效果:\n{result.stdout}")
    print("  注意: 'Start' 和 'Item 0' 之间无明确边界，修复不完美")

    # 测试5: 带空格分隔的混合输出（更容易修复）
    print("\n【测试5】带空格分隔的混合输出")
    code = '''
print("Start - ", end="")
for i in range(3):
    print(f"Item {i} ", end="")
print("End")
'''
    result = await sandbox.execute(code)
    print(f"修复前（原始）: {repr(result.raw_result.stdout)}")
    print(f"修复后: {repr(result.stdout)}")

    # 测试6: 与原始行为对比
    print("\n【测试6】与原始 PyodideSandbox 对比")
    from langchain_sandbox import PyodideSandbox

    original = PyodideSandbox(allow_net=True)
    fixed = FixedPyodideSandbox(allow_net=True)

    test_cases = [
        ("简单print", 'print("A")\nprint("B")\nprint("C")'),
        ("循环print", 'for i in range(5):\n    print(f"Iteration {i}")'),
        ("混合输出", 'print("Start")\nfor i in range(3):\n    print(f"Item {i}")\nprint("End")'),
    ]

    for name, code in test_cases:
        print(f"\n{name}:")
        orig_result = await original.execute(code)
        fixed_result = await fixed.execute(code)

        orig_lines = orig_result.stdout.count('') if orig_result.stdout else 0
        fixed_lines = fixed_result.stdout.count('\n') + 1 if fixed_result.stdout else 0

        print(f"  原始: {repr(orig_result.stdout[:50])}... ({len(orig_result.stdout) if orig_result.stdout else 0} chars)")
        print(f"  修复: {repr(fixed_result.stdout[:50])}... ({fixed_lines} lines detected)")


if __name__ == "__main__":
    asyncio.run(test_fix())
