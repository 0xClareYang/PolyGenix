#!/usr/bin/env bash
set -euo pipefail

if [ -n "${REVIEW_ROOT:-}" ]; then
  ROOT_DIR="$REVIEW_ROOT"
else
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  fi
fi
if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] $PYTHON_BIN not found"
  exit 1
fi

cn_date="$("$PYTHON_BIN" - <<'PY'
from datetime import datetime, timedelta, timezone
print(datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_CN"))
PY
)"

out_dir="out/review/${cn_date}"
mkdir -p "$out_dir"

export CN_DATE="$cn_date"

latest_compare="$(ls -t out/evolution/*/compare.md 2>/dev/null | head -n 1 || true)"
if [ -n "$latest_compare" ]; then
  cp "$latest_compare" "$out_dir/compare.md"
fi

if [ -f "out/evolution/state.json" ]; then
  cp "out/evolution/state.json" "$out_dir/state.json"
fi

if [ -f "logs/polymarket.log" ]; then
  tail -n 200 logs/polymarket.log > "$out_dir/polymarket_tail.log"
  "$PYTHON_BIN" tools/evolution/redact.py --in "$out_dir/polymarket_tail.log" --out "$out_dir/polymarket_tail.log"
fi

if [ -f "reports/pipeline_status.json" ]; then
  cp "reports/pipeline_status.json" "$out_dir/pipeline_status.json"
fi

summary_path="$out_dir/SUMMARY.md"
"$PYTHON_BIN" - <<'PY'
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

cn_tz = timezone(timedelta(hours=8))
root = Path(".")

state = {}
state_path = root / "out" / "evolution" / "state.json"
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        state = {}

health_path = None
health = {}
for path in (root / "out" / "guardian").rglob("health.json"):
    health_path = path
if health_path and health_path.exists():
    try:
        health = json.loads(health_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        health = {}

last_status_path = root / "out" / "guardian" / "last_status.json"
last_status = {}
if last_status_path.exists():
    try:
        last_status = json.loads(last_status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        last_status = {}

compare_path = None
for path in (root / "out" / "evolution").rglob("compare.md"):
    compare_path = path

cn_date = os.environ.get("CN_DATE", "UNKNOWN")
lines = []
lines.append("# Daytime Review Summary")
lines.append("")
lines.append(f"- date: {datetime.now(cn_tz).date().isoformat()}")
if compare_path:
    lines.append(f"- latest_compare: {compare_path}")
lines.append(f"- frozen: {state.get('frozen')}")
lines.append(f"- failure_streak: {state.get('failure_streak')}")
lines.append(f"- best_score: {state.get('best_score')}")
lines.append("")
lines.append("## Guardian Health (latest)")
if health_path:
    lines.append(f"- health_path: {health_path}")
    lines.append(f"- healthy: {health.get('healthy')}")
    rates = health.get("rates") or {}
    lines.append(f"- http_success_rate: {rates.get('http_success_rate')}")
    lines.append(f"- error_rate: {rates.get('error_rate')}")
    lines.append(f"- signal_rate: {rates.get('signal_rate')}")
else:
    lines.append("- health_path: (none)")
lines.append("")
lines.append("## Guardian Last Status")
if last_status:
    for key, value in last_status.items():
        lines.append(f"- {key}: {value}")
else:
    lines.append("- last_status: (none)")
lines.append("")
lines.append("## Manual Decision Override")
lines.append("- To force a patch, create DECISION.env in this folder.")
lines.append("- Format: KEY=VALUE per line (no secrets).")

(Path("out/review") / cn_date / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
PY

if [ "${OPEN_REVIEW:-0}" = "1" ]; then
  if [ -f "$out_dir/SUMMARY.md" ]; then
    open "$out_dir/SUMMARY.md" || true
  fi
  if [ -f "$out_dir/compare.md" ]; then
    open "$out_dir/compare.md" || true
  fi
fi

echo "[review] $out_dir"
