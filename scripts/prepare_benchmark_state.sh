#!/usr/bin/env bash
set -euo pipefail

BRANCH_NAME="${1:-experiment/benchmark-baseline}"
TARGET_DIR="${2:-workspace}"
SNAPSHOT_DIR="${3:-workspace_snapshot}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Current directory is not a git repository."
  exit 1
fi

echo "[1/4] Creating/switching branch: $BRANCH_NAME"
git checkout -B "$BRANCH_NAME"

echo "[2/4] Stashing working tree changes (including untracked files)"
git stash push -u -m "benchmark-prepare-$(date +%Y%m%d_%H%M%S)"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Target directory '$TARGET_DIR' does not exist."
  echo "Tip: pass repository root as target if you want full snapshot."
  exit 1
fi

echo "[3/4] Rebuilding snapshot: $SNAPSHOT_DIR"
rm -rf "$SNAPSHOT_DIR"
cp -r "$TARGET_DIR" "$SNAPSHOT_DIR"

echo "[4/4] Done"
echo "To reset before each run:"
echo "  ./scripts/reset_workspace_snapshot.sh '$TARGET_DIR' '$SNAPSHOT_DIR'"
