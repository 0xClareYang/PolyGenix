#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  fi
fi
echo "[demo] PYTHON_BIN=$PYTHON_BIN"
"$PYTHON_BIN" --version

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] $PYTHON_BIN not found. Please create the repo-local venv first."
  exit 1
fi

mkdir -p logs reports out/evolution/baseline

export PYTHONPATH=src
export RUNNER_FETCH_MODE=light
export POLY_DRY_RUN=true
export PAPER_TRADING=1
export ONE_LOOP=1
export SKIP_FETCH_PREFLIGHT=1
export SERVICE_REST_MAX_CONCURRENCY=1
export SERVICE_REST_RATE_LIMIT_PER_SEC=0.3
export NEWS_FORCE_REFRESH=0
export NEWS_BOOTSTRAP_TTL_SECS=600
export NEWS_BOOTSTRAP_TIMEOUT_SECS=30
export DEMO_ALPHA_MODE=balanced
export DEMO_EDGE_BPS=80
export DEMO_MAX_SPREAD_BPS=400

RUN_MODE="${EVOLVE_RUN_MODE:-demo_light}"
launcher_module="apps.launcher_demo"
if [ "$RUN_MODE" = "real_dryrun" ]; then
  launcher_module="apps.launcher_real_dryrun"
elif [ "$RUN_MODE" = "live_light" ] || [ "${EVOLVE_LIVE_LIGHT:-0}" = "1" ]; then
  launcher_module="apps.launcher_live_light"
fi

proxy_vars=(ALL_PROXY HTTP_PROXY HTTPS_PROXY PROXY_URL CLOB_WS_PROXY_URL)
proxy_line="[proxy_effective]"
proxy_any=0
for name in "${proxy_vars[@]}"; do
  if [ -n "${!name-}" ]; then
    proxy_any=1
    proxy_line+=" ${name}=<set>"
  else
    proxy_line+=" ${name}=<unset>"
  fi
  done
if [ $proxy_any -eq 1 ]; then
  echo "$proxy_line"
fi

BASELINE_DIR="out/evolution/baseline"

set +e
"$PYTHON_BIN" -u -m "$launcher_module" trade --interval 60 --log-level INFO --max-loops 1 \
  1> "${BASELINE_DIR}/baseline_stdout.log" 2> "${BASELINE_DIR}/baseline_stderr.log"
exit_code=$?
set -e

echo "[baseline] exit_code=${exit_code}"
export BASELINE_EXIT_CODE="$exit_code"

"$PYTHON_BIN" tools/evolution/parse_run_id.py \
  --root out/evolution \
  --log logs/polymarket.log \
  --output "${BASELINE_DIR}/run_id.json" || true

"$PYTHON_BIN" - <<'PY'
from pathlib import Path
import json
import os
import re

root = Path(".")
base_dir = root / "out" / "evolution" / "baseline"
run_id_info = None
run_id_path = base_dir / "run_id.json"
if run_id_path.exists():
    try:
        run_id_info = json.loads(run_id_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        run_id_info = None

artifacts = {}
missing = {}
for path in [
    root / "logs" / "polymarket.log",
    root / "logs" / "trade_journal.jsonl",
    root / "reports" / "pipeline_status.json",
]:
    key = str(path)
    if path.exists():
        artifacts[key] = "present"
    else:
        artifacts[key] = "missing"
        missing[key] = "file missing"

phaseb_dir = root / "reports" / "phaseB"
if phaseb_dir.exists():
    candidates = sorted(phaseb_dir.glob("typea_candidates_*.csv"))
    if candidates:
        artifacts["reports/phaseB/typea_candidates_*.csv"] = str(candidates[-1])
    else:
        missing["reports/phaseB/typea_candidates_*.csv"] = "no candidates csv"
else:
    missing["reports/phaseB/typea_candidates_*.csv"] = "phaseB dir missing"

exit_code = int(os.environ.get("BASELINE_EXIT_CODE", "1"))

payload = {
    "run_tag": "baseline",
    "exit_code": exit_code,
    "run_id": run_id_info.get("run_id") if run_id_info else None,
    "run_id_source": run_id_info.get("source") if run_id_info else None,
    "run_id_confidence": run_id_info.get("confidence") if run_id_info else None,
    "artifacts": artifacts,
    "missing": missing,
}

if exit_code != 0:
    payload["error"] = "baseline run failed; see baseline_stderr.log"
    stderr_path = base_dir / "baseline_stderr.log"
    if stderr_path.exists():
        text = stderr_path.read_text(encoding="utf-8", errors="replace")
        patterns = [
            (re.compile(r"timeout", re.IGNORECASE), "timeout"),
            (re.compile(r"429"), "rate_limit"),
            (re.compile(r"connection reset", re.IGNORECASE), "connection_reset"),
            (re.compile(r"connection aborted", re.IGNORECASE), "connection_aborted"),
            (re.compile(r"max retries", re.IGNORECASE), "max_retries"),
        ]
        reason = None
        for pattern, label in patterns:
            if pattern.search(text):
                reason = label
                break
        payload["error_reason"] = reason or "unknown"

baseline_artifacts = base_dir / "baseline_artifacts.json"
baseline_artifacts.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
print(f"[baseline] wrote {baseline_artifacts}")
PY

for path in logs/polymarket.log logs/trade_journal.jsonl reports/pipeline_status.json; do
  if [ -f "$path" ]; then
    echo "[artifact] $path"
  else
    echo "[missing] $path"
  fi
done

if ls reports/phaseB/typea_candidates_*.csv >/dev/null 2>&1; then
  echo "[artifact] reports/phaseB/typea_candidates_*.csv"
else
  echo "[missing] reports/phaseB/typea_candidates_*.csv"
fi

exit $exit_code
