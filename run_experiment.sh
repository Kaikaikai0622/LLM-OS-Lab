#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
if [[ -z "$MODE" ]]; then
  echo "Usage: ./run_experiment.sh <baseline|context_mode> [backend]"
  exit 1
fi

if [[ "$MODE" != "baseline" && "$MODE" != "context_mode" ]]; then
  echo "Invalid mode: $MODE"
  echo "Expected: baseline | context_mode"
  exit 1
fi

BACKEND="${2:-pyodide}"
if [[ "$BACKEND" != "pyodide" && "$BACKEND" != "local" ]]; then
  echo "Invalid backend: $BACKEND"
  echo "Expected: pyodide | local"
  exit 1
fi

RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="logs/${MODE}_${RUN_ID}.json"

# Activate venv without relying on prior shell session state.
if [[ -f ".venv/Scripts/activate" ]]; then
  # Git Bash on Windows
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
elif [[ -f ".venv/bin/activate" ]]; then
  # Linux/macOS
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "Cannot find virtual environment activation script under .venv/"
  exit 1
fi

python main.py \
  --mode "$MODE" \
  --backend "$BACKEND" \
  --max-executions 25 \
  --timeout 15 \
  --total-timeout 120 \
  --summary-max-chars 500 \
  --log-file "$LOG_FILE" \
  --task-file experiment_tasks/benchmark_tasks.txt

echo "Done: $LOG_FILE"
