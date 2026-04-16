#!/bin/bash
# xdigest launcher for launchd
# Runs the xdigest pipeline with proper environment

set -euo pipefail

export PATH="/opt/homebrew/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"
LOG_DIR="$HOME/.config/espelho/xdigest/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/$(date -u +%Y-%m-%dT%H-%M-%S).log"

# Change to the mirror repo root (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "=== xdigest run started at $(date) ===" >> "$LOG_FILE"
/opt/homebrew/bin/uv run xdigest >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "=== xdigest run finished at $(date) with exit code $EXIT_CODE ===" >> "$LOG_FILE"

# Keep only last 30 log files
ls -t "$LOG_DIR"/*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

exit $EXIT_CODE
