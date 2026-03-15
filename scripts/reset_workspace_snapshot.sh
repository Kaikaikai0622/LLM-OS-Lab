#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-workspace}"
SNAPSHOT_DIR="${2:-workspace_snapshot}"

if [[ ! -d "$SNAPSHOT_DIR" ]]; then
  echo "Snapshot directory '$SNAPSHOT_DIR' does not exist."
  exit 1
fi

rm -rf "$TARGET_DIR"
cp -r "$SNAPSHOT_DIR" "$TARGET_DIR"

echo "Reset done: $TARGET_DIR <- $SNAPSHOT_DIR"
