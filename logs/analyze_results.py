#!/usr/bin/env python3
"""Analyze and compare benchmark results"""
import json
import re
from pathlib import Path

def parse_log(filepath):
    """Parse a log file and extract key metrics"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = []
    for result in data['results']:
        stdout = result['stdout']

        # Extract execution count
        exec_match = re.search(r'execution_count=(\d+)', stdout)
        execution_count = int(exec_match.group(1)) if exec_match else 0

        # Extract stop reason
        stop_match = re.search(r'stop_reason=([a-z_]+)', stdout)
        stop_reason = stop_match.group(1) if stop_match else 'unknown'

        # Extract elapsed time
        time_match = re.search(r'elapsed_seconds=([\d.]+)', stdout)
        elapsed = float(time_match.group(1)) if time_match else 0

        # Extract total tokens (last cum(total=XXX) in the output)
        token_matches = re.findall(r'cum\(total=(\d+)\)', stdout)
        total_tokens = int(token_matches[-1]) if token_matches else 0

        # Extract max prompt tokens
        max_prompt_match = re.search(r'max_prompt_tokens:\s*(\d+)', stdout)
        max_prompt = int(max_prompt_match.group(1)) if max_prompt_match else 0

        # Get task name (first 50 chars)
        task = result['task'][:50] + '...' if len(result['task']) > 50 else result['task']

        results.append({
            'task': task,
            'execution_count': execution_count,
            'stop_reason': stop_reason,
            'elapsed_seconds': elapsed,
            'total_tokens': total_tokens,
            'max_prompt_tokens': max_prompt,
            'duration_seconds': result.get('duration_seconds', 0)
        })

    return results

def main():
    baseline_file = Path(__file__).parent / 'baseline_subset5_20260315_032634.json'
    context_file = Path(__file__).parent / 'context_mode_subset5_20260315_032854.json'

    baseline = parse_log(baseline_file)
    context = parse_log(context_file)

    print("=" * 100)
    print("BENCHMARK RESULTS COMPARISON: Baseline vs Context Mode (v2 Tasks)")
    print("=" * 100)
    print(f"{'Task':<50} | {'Mode':<8} | {'Execs':<5} | {'Stop':<15} | {'Time(s)':<8} | {'Tokens':<8}")
    print("-" * 100)

    task_names = [
        "Fibonacci 计算",
        "矩阵特征值统计",
        "素数统计",
        "高斯消元过程",
        "梯形积分收敛"
    ]

    total_baseline_execs = 0
    total_context_execs = 0
    total_baseline_tokens = 0
    total_context_tokens = 0
    total_baseline_time = 0
    total_context_time = 0

    for i, (bl, cm) in enumerate(zip(baseline, context)):
        task_name = task_names[i] if i < len(task_names) else f"Task {i+1}"

        # Baseline row
        print(f"{task_name:<50} | {'BL':<8} | {bl['execution_count']:<5} | {bl['stop_reason']:<15} | {bl['elapsed_seconds']:<8.1f} | {bl['total_tokens']:<8}")

        # Context Mode row
        print(f"{'':<50} | {'CM':<8} | {cm['execution_count']:<5} | {cm['stop_reason']:<15} | {cm['elapsed_seconds']:<8.1f} | {cm['total_tokens']:<8}")

        print("-" * 100)

        total_baseline_execs += bl['execution_count']
        total_context_execs += cm['execution_count']
        total_baseline_tokens += bl['total_tokens']
        total_context_tokens += cm['total_tokens']
        total_baseline_time += bl['elapsed_seconds']
        total_context_time += cm['elapsed_seconds']

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"{'Metric':<30} | {'Baseline':<15} | {'Context Mode':<15} | {'Diff':<15}")
    print("-" * 100)

    exec_diff = ((total_context_execs - total_baseline_execs) / total_baseline_execs * 100) if total_baseline_execs > 0 else 0
    token_diff = ((total_context_tokens - total_baseline_tokens) / total_baseline_tokens * 100) if total_baseline_tokens > 0 else 0
    time_diff = ((total_context_time - total_baseline_time) / total_baseline_time * 100) if total_baseline_time > 0 else 0

    print(f"{'Total Executions':<30} | {total_baseline_execs:<15} | {total_context_execs:<15} | {exec_diff:>+14.1f}%")
    print(f"{'Total Tokens':<30} | {total_baseline_tokens:<15} | {total_context_tokens:<15} | {token_diff:>+14.1f}%")
    print(f"{'Total Time (s)':<30} | {total_baseline_time:<15.1f} | {total_context_time:<15.1f} | {time_diff:>+14.1f}%")

    print("\n" + "=" * 100)
    print("ANALYSIS")
    print("=" * 100)

    # Analyze each task
    for i, (bl, cm) in enumerate(zip(baseline, context)):
        task_name = task_names[i] if i < len(task_names) else f"Task {i+1}"

        if cm['execution_count'] < bl['execution_count']:
            print(f"✅ {task_name}: CM 更优 (执行次数 {cm['execution_count']} < {bl['execution_count']})")
        elif cm['execution_count'] > bl['execution_count']:
            print(f"⚠️  {task_name}: CM 劣化 (执行次数 {cm['execution_count']} > {bl['execution_count']})")
        else:
            if cm['total_tokens'] < bl['total_tokens']:
                print(f"✅ {task_name}: 次数相同，CM token 更少 ({cm['total_tokens']} < {bl['total_tokens']})")
            else:
                print(f"⚠️  {task_name}: 次数相同，但 CM token 更多 ({cm['total_tokens']} > {bl['total_tokens']})")

    print("\n" + "=" * 100)
    print("KEY FINDINGS")
    print("=" * 100)

    # Overall assessment
    if total_context_execs <= total_baseline_execs and total_context_tokens <= total_baseline_tokens:
        print("🎉 优化成功！Context Mode 在任务完成效率上优于 Baseline")
    elif total_context_execs <= total_baseline_execs * 1.1:
        print("✅ 基本达成目标。Context Mode 执行效率与 Baseline 相当")
    else:
        print("⚠️ 仍需优化。Context Mode 执行次数明显高于 Baseline")

if __name__ == "__main__":
    main()
