#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

def parse_log(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)

    results = []
    for result in data['results']:
        stdout = result['stdout']

        exec_match = re.search(r'execution_count=(\d+)', stdout)
        execution_count = int(exec_match.group(1)) if exec_match else 0

        stop_match = re.search(r'stop_reason=([a-z_]+)', stdout)
        stop_reason = stop_match.group(1) if stop_match else 'unknown'

        time_match = re.search(r'elapsed_seconds=([\d.]+)', stdout)
        elapsed = float(time_match.group(1)) if time_match else 0

        token_matches = re.findall(r'cum\(total=(\d+)\)', stdout)
        total_tokens = int(token_matches[-1]) if token_matches else 0

        max_prompt_match = re.search(r'max_prompt_tokens:\s*(\d+)', stdout)
        max_prompt = int(max_prompt_match.group(1)) if max_prompt_match else 0

        task = result['task'][:40] + '...' if len(result['task']) > 40 else result['task']

        results.append({
            'task': task,
            'execution_count': execution_count,
            'stop_reason': stop_reason,
            'elapsed_seconds': elapsed,
            'total_tokens': total_tokens,
            'max_prompt_tokens': max_prompt,
        })

    return results

def main():
    naive = parse_log('native_minimal_20260315_055909.json')
    baseline = parse_log('baseline_minimal_20260315_060026.json')
    context = parse_log('context_mode_minimal_20260315_060108.json')

    print('=' * 100)
    print('MINIMAL TEST RESULTS: Naive vs Baseline vs Context Mode')
    print('=' * 100)
    print(f'{"Task":<43} | {"Mode":<8} | {"Execs":<5} | {"Stop":<15} | {"Time(s)":<8} | {"Tokens":<7} | {"MaxPrompt":<10}')
    print('-' * 100)

    task_names = ['Task 1: Fibonacci', 'Task 7: Maze BFS']

    for i in range(2):
        task_name = task_names[i]
        n = naive[i]
        b = baseline[i]
        c = context[i]

        print(f'{task_name:<43} | {"NAIVE":<8} | {n["execution_count"]:<5} | {n["stop_reason"]:<15} | {n["elapsed_seconds"]:<8.1f} | {n["total_tokens"]:<7} | {n["max_prompt_tokens"]}')
        print(f'{" "*43} | {"BASELINE":<8} | {b["execution_count"]:<5} | {b["stop_reason"]:<15} | {b["elapsed_seconds"]:<8.1f} | {b["total_tokens"]:<7} | {b["max_prompt_tokens"]}')
        print(f'{" "*43} | {"CONTEXT":<8} | {c["execution_count"]:<5} | {c["stop_reason"]:<15} | {c["elapsed_seconds"]:<8.1f} | {c["total_tokens"]:<7} | {c["max_prompt_tokens"]}')
        print('-' * 100)

    print()
    print('=' * 100)
    print('SUMMARY')
    print('=' * 100)

    for mode_name, data in [('NAIVE', naive), ('BASELINE', baseline), ('CONTEXT', context)]:
        total_execs = sum(r['execution_count'] for r in data)
        total_tokens = sum(r['total_tokens'] for r in data)
        total_time = sum(r['elapsed_seconds'] for r in data)
        print(f'{mode_name:<10} | Total Execs: {total_execs:<3} | Total Tokens: {total_tokens:<6} | Total Time: {total_time:<6.1f}s')

    print()
    print('=' * 100)
    print('KEY OBSERVATIONS')
    print('=' * 100)

    naive_tokens = sum(r['total_tokens'] for r in naive)
    baseline_tokens = sum(r['total_tokens'] for r in baseline)
    context_tokens = sum(r['total_tokens'] for r in context)

    print(f'1. Token Usage (Naive vs Baseline): {naive_tokens} vs {baseline_tokens} ({(naive_tokens/baseline_tokens-1)*100:+.1f}%)')
    print(f'2. Token Usage (Context vs Baseline): {context_tokens} vs {baseline_tokens} ({(context_tokens/baseline_tokens-1)*100:+.1f}%)')

    all_ok = all(r['stop_reason'] == 'no_tool_calls' for r in naive + baseline + context)
    print(f'3. All tasks completed successfully: {all_ok}')

    # Per-task analysis
    print()
    print('PER-TASK ANALYSIS:')
    print('-' * 100)

    for i, task_name in enumerate(['Fibonacci', 'Maze BFS']):
        print(f'{task_name}:')
        n, b, c = naive[i], baseline[i], context[i]

        # Execution count comparison
        if n['execution_count'] == b['execution_count'] == c['execution_count']:
            print(f'  - Execution count: All modes used {n["execution_count"]} executions')
        else:
            print(f'  - Execution count: Naive={n["execution_count"]}, Baseline={b["execution_count"]}, Context={c["execution_count"]}')

        # Token comparison
        token_ratio_n = (n['total_tokens'] / b['total_tokens'] - 1) * 100 if b['total_tokens'] > 0 else 0
        token_ratio_c = (c['total_tokens'] / b['total_tokens'] - 1) * 100 if b['total_tokens'] > 0 else 0
        print(f'  - Token overhead: Naive {token_ratio_n:+.1f}%, Context {token_ratio_c:+.1f}% vs Baseline')

        # Time comparison
        time_ratio_n = (n['elapsed_seconds'] / b['elapsed_seconds'] - 1) * 100 if b['elapsed_seconds'] > 0 else 0
        time_ratio_c = (c['elapsed_seconds'] / b['elapsed_seconds'] - 1) * 100 if b['elapsed_seconds'] > 0 else 0
        print(f'  - Time overhead: Naive {time_ratio_n:+.1f}%, Context {time_ratio_c:+.1f}% vs Baseline')
        print()

if __name__ == '__main__':
    main()
