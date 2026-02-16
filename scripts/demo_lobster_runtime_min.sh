#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  fi
fi

LOBSTER_BIN=""
LOBSTER_BIN_ENV="${LOBSTER_BIN:-}"
if [ -n "${EVOLVE_LOBSTER_PATH:-}" ] && [ -x "${EVOLVE_LOBSTER_PATH:-}" ]; then
  LOBSTER_BIN="$EVOLVE_LOBSTER_PATH"
elif [ -n "$LOBSTER_BIN_ENV" ] && [ -x "$LOBSTER_BIN_ENV" ]; then
  LOBSTER_BIN="$LOBSTER_BIN_ENV"
elif [ -f "out/evolution/runtime_probe/lobster_wrapper_path.txt" ]; then
  wrapper_path="$(cat out/evolution/runtime_probe/lobster_wrapper_path.txt)"
  if [ -x "$wrapper_path" ]; then
    LOBSTER_BIN="$wrapper_path"
  fi
elif command -v lobster >/dev/null 2>&1; then
  LOBSTER_BIN="$(command -v lobster)"
fi

if [ -z "$LOBSTER_BIN" ] || [ ! -x "$LOBSTER_BIN" ]; then
  echo "[error] lobster CLI not found. Set EVOLVE_LOBSTER_PATH or LOBSTER_BIN." >&2
  exit 2
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] PYTHON_BIN not found: $PYTHON_BIN" >&2
  exit 3
fi

ts=$(date +%Y%m%d_%H%M%S_%N)
out_dir="out/evolution/runtime_runs/$ts"
mkdir -p "$out_dir"

pipeline="exec --json --shell 'echo [1]' | approve --prompt 'ok?'"
run_out="$out_dir/min_runtime_run.json"
resume_out="$out_dir/min_runtime_resume.json"

"$LOBSTER_BIN" run --mode tool "$pipeline" > "$run_out"

token="$("$PYTHON_BIN" - "$run_out" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
resume = data.get("requiresApproval") or {}
print(resume.get("resumeToken") or "")
PY
)"

if [ -z "$token" ]; then
  echo "[error] resumeToken missing from lobster run output" >&2
  exit 4
fi

"$LOBSTER_BIN" resume --token "$token" --approve yes > "$resume_out"

status="$("$PYTHON_BIN" - "$resume_out" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("status") or "")
PY
)"

if [ "$status" != "ok" ]; then
  echo "[error] lobster resume status=$status" >&2
  exit 5
fi

echo "runtime_min_ok" > "$out_dir/min_runtime_ok.txt"
echo "[ok] lobster runtime min check passed: $out_dir/min_runtime_ok.txt"
