#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  fi
fi
echo "[daily] PYTHON_BIN=$PYTHON_BIN"
"$PYTHON_BIN" --version

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] $PYTHON_BIN not found. Please create the repo-local venv first."
  exit 1
fi

mkdir -p out/evolution/daily

if [ -x "scripts/probe_openclaw_runtime.sh" ]; then
  ./scripts/probe_openclaw_runtime.sh || true
fi

max_candidates="${EVOLVE_DAILY_MAX_CANDIDATES:-3}"
review_path="$("$PYTHON_BIN" tools/evolution/daily_driver.py --output-root out/evolution/daily --max-candidates "$max_candidates")"
echo "[daily] review=$review_path"
echo "$review_path"
