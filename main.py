import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def load_tasks(task_file: Path) -> list[str]:
    tasks: list[str] = []
    for line in task_file.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        tasks.append(item)
    return tasks


def run_single_task(task: str, args: argparse.Namespace) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "agent",
        task,
        "--max-executions",
        str(args.max_executions),
        "--timeout",
        str(args.timeout),
        "--total-timeout",
        str(args.total_timeout),
        "--summary-max-chars",
        str(args.summary_max_chars),
        "--verbose",
    ]

    if args.mode == "native":
        cmd.append("--no-index")
        cmd.extend(["--summary-max-chars", "999999"])  # 不截断
    elif args.mode == "baseline":
        # 启用索引+消息压缩，但不向 LLM 暴露 fetch_execution_detail 工具
        cmd.append("--no-fetch-tool")
    # context_mode: 不加任何 flag，使用默认 InMemoryIndexStore + fetch 工具

    env = dict(**subprocess.os.environ)
    env["AGENT_EXECUTION_BACKEND"] = args.backend

    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = round(time.perf_counter() - started, 3)

    # 从 stdout 解析 round_token_history
    round_token_history = []
    for line in (proc.stdout or "").splitlines():
        if line.startswith("ROUND_TOKEN_HISTORY_JSON:"):
            try:
                round_token_history = json.loads(line[len("ROUND_TOKEN_HISTORY_JSON:"):])
            except json.JSONDecodeError:
                pass
            break

    return {
        "task": task,
        "return_code": proc.returncode,
        "duration_seconds": elapsed,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": cmd,
        "round_token_history": round_token_history,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark tasks in stable conditions")
    parser.add_argument("--mode", choices=["native", "baseline", "context_mode"], required=True)
    parser.add_argument("--max-executions", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--total-timeout", type=int, default=120)
    parser.add_argument("--summary-max-chars", type=int, default=500)
    parser.add_argument("--task-file", default="experiment_tasks/benchmark_tasks.txt")
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--backend", choices=["pyodide", "local"], default="pyodide")
    args = parser.parse_args()

    task_file = Path(args.task_file)
    tasks = load_tasks(task_file)
    if not tasks:
        raise SystemExit(f"No tasks found in {task_file}")

    log_file = Path(args.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    run_started_at = datetime.now().isoformat(timespec="seconds")
    results: list[dict] = []

    for index, task in enumerate(tasks, start=1):
        print(f"[{index}/{len(tasks)}] Running: {task[:80]}")
        item = run_single_task(task, args)
        item["index"] = index
        results.append(item)

    payload = {
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "backend": args.backend,
        "config": {
            "max_executions": args.max_executions,
            "timeout": args.timeout,
            "total_timeout": args.total_timeout,
            "summary_max_chars": args.summary_max_chars,
            "task_file": str(task_file),
        },
        "task_count": len(tasks),
        "results": results,
    }

    log_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done: {log_file}")


if __name__ == "__main__":
    main()
