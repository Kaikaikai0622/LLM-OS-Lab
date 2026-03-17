"""
统一日志解析模块 — 从 logs/*.json 解析实验数据为 pandas DataFrame。

被 Streamlit Dashboard 全部页面共用。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

def _extract_int(pattern: str, text: str, default: int = 0) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else default


def _extract_float(pattern: str, text: str, default: float = 0.0) -> float:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else default


def _extract_str(pattern: str, text: str, default: str = "unknown") -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else default


def _extract_last_int(pattern: str, text: str, default: int = 0) -> int:
    matches = re.findall(pattern, text)
    return int(matches[-1]) if matches else default


# ---------------------------------------------------------------------------
# 核心解析
# ---------------------------------------------------------------------------

def parse_log_file(filepath: Path) -> list[dict]:
    """解析单个日志文件为 flat records 列表。"""
    data = json.loads(filepath.read_text("utf-8"))
    mode = data.get("mode", "unknown")
    model = data.get("model", "(env default)")
    config = data.get("config", {})
    log_name = filepath.stem

    records = []
    for r in data.get("results", []):
        stdout = r.get("stdout", "")
        metrics = r.get("metrics", {})
        rth = r.get("round_token_history", [])

        # 优先从 METRICS_JSON 取值，fallback 到 stdout regex
        execution_count = metrics.get(
            "execution_count",
            _extract_int(r"execution_count=(\d+)", stdout),
        )
        stop_reason = metrics.get(
            "stop_reason",
            _extract_str(r"stop_reason=([a-z_]+)", stdout),
        )
        elapsed_seconds = metrics.get(
            "elapsed_seconds",
            _extract_float(r"elapsed_seconds=([\d.]+)", stdout),
        )
        total_tokens = metrics.get(
            "llm_total_tokens",
            _extract_last_int(r"cum\(total=(\d+)\)", stdout),
        )
        max_prompt_tokens = metrics.get(
            "max_prompt_tokens",
            _extract_int(r"max_prompt_tokens:\s*(\d+)", stdout),
        )
        task_success = metrics.get(
            "task_success",
            stop_reason == "no_tool_calls",
        )
        compression_ratio = metrics.get("compression_ratio", 0.0)
        fetch_hit_count = metrics.get("fetch_hit_count", 0)

        record = {
            # 维度
            "log_file": log_name,
            "mode": mode,
            "model": model,
            "task_index": r.get("index", 0),
            "task": r.get("task", "")[:80],
            # 指标
            "execution_count": execution_count,
            "stop_reason": stop_reason,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "total_tokens": total_tokens,
            "prompt_tokens": metrics.get("llm_prompt_tokens", 0),
            "completion_tokens": metrics.get("llm_completion_tokens", 0),
            "max_prompt_tokens": max_prompt_tokens,
            "task_success": task_success,
            "compression_ratio": compression_ratio,
            "fetch_hit_count": fetch_hit_count,
            "duration_seconds": round(r.get("duration_seconds", 0), 2),
            "round_count": len(rth),
            "round_token_history": rth,
            # 配置
            "config_max_exec": config.get("max_executions"),
            "config_timeout": config.get("total_timeout"),
            "config_task_file": config.get("task_file", ""),
        }
        records.append(record)
    return records


def load_all_logs(log_dir: str | Path = "logs") -> pd.DataFrame:
    """扫描目录下所有 *.json，返回合并 DataFrame。"""
    log_path = Path(log_dir)
    all_records: list[dict] = []
    for f in sorted(log_path.glob("*.json")):
        try:
            all_records.extend(parse_log_file(f))
        except (json.JSONDecodeError, KeyError):
            continue
    if not all_records:
        return pd.DataFrame()
    df = pd.DataFrame(all_records)
    # 友好标签
    df["mode_label"] = df["mode"].map({
        "native": "Native",
        "baseline": "Baseline",
        "context_mode": "Context Mode",
    }).fillna(df["mode"])
    df["status_emoji"] = df["task_success"].map({True: "✅", False: "❌"})
    return df


def load_single_log(filepath: str | Path) -> dict:
    """加载单个 JSON 日志文件的原始 dict。"""
    return json.loads(Path(filepath).read_text("utf-8"))


def get_available_logs(log_dir: str | Path = "logs") -> list[Path]:
    """返回 logs 目录下所有 JSON 文件路径。"""
    return sorted(Path(log_dir).glob("*.json"))
