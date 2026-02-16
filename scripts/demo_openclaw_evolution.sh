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

mkdir -p out/evolution

if [ "${EVOLVE_USE_LOBSTER_RUNTIME:-0}" = "1" ]; then
  echo "[demo] EVOLVE_USE_LOBSTER_RUNTIME=1 -> using Lobster runtime"
  lobster_args=()
  if [ -n "${EVOLVE_LOBSTER_PATH:-}" ]; then
    lobster_args+=(--lobster-bin "$EVOLVE_LOBSTER_PATH")
  elif [ -n "${LOBSTER_BIN:-}" ]; then
    lobster_args+=(--lobster-bin "$LOBSTER_BIN")
  else
    if [ -x "$PYTHON_BIN" ]; then
      IFS=$'\t' read -r runtime_cli_name runtime_cli_path lobster_mode lobster_path < <("$PYTHON_BIN" - <<'PY'
from tools.evolution.cli_locator import locate_cli

data = locate_cli()
runtime_name = data.get("runtime_cli_name") or "missing"
runtime_path = data.get("runtime_cli_path") or "none"
lobster_mode = data.get("lobster_mode") or "missing"
lobster_path = data.get("lobster_path") or "none"
print(f"{runtime_name}\t{runtime_path}\t{lobster_mode}\t{lobster_path}")
PY
)
      echo "[demo] cli_locator runtime=$runtime_cli_name lobster_mode=$lobster_mode"
      if [ "${lobster_mode:-}" = "standalone" ] && [ -n "$lobster_path" ] && [ "$lobster_path" != "none" ]; then
        lobster_args+=(--lobster-bin "$lobster_path")
        export EVOLVE_LOBSTER_PATH="$lobster_path"
      elif [ "${lobster_mode:-}" = "subcommand" ] && [ -n "$runtime_cli_path" ] && [ "$runtime_cli_path" != "none" ]; then
        lobster_args+=(--runtime-cli "$runtime_cli_path")
      fi
    fi
  fi
  "$PYTHON_BIN" tools/evolution/run_lobster_workflow.py \
    --workflow workflows/pm_evolution_demo.lobster \
    "${lobster_args[@]}"
  runtime_rc=$?
  if [ $runtime_rc -ne 0 ]; then
    echo "[error] lobster runtime failed (exit_code=$runtime_rc)"
    exit $runtime_rc
  fi
  result_line_path=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path

root = Path("out/evolution/runtime_runs")
latest = None
for path in root.rglob("result_line.txt"):
    try:
        stat = path.stat()
    except FileNotFoundError:
        continue
    if latest is None or stat.st_mtime > latest[0]:
        latest = (stat.st_mtime, path)

if latest is None:
    print("")
else:
    print(str(latest[1]))
PY
)
  if [ -n "$result_line_path" ] && [ -f "$result_line_path" ]; then
    echo "result_line_path=$result_line_path"
    result_line="$(cat "$result_line_path")"
    if [ -n "$result_line" ]; then
      echo "$result_line"
      exit 0
    fi
  fi
  compare_path=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path

root = Path("out/evolution")
latest = None
for path in root.rglob("compare.md"):
    try:
        stat = path.stat()
    except FileNotFoundError:
        continue
    if latest is None or stat.st_mtime > latest[0]:
        latest = (stat.st_mtime, path)

if latest is None:
    print("")
else:
    print(str(latest[1]))
PY
)
  if [ -z "$compare_path" ] || [ ! -f "$compare_path" ]; then
    echo "[error] compare.md not found after lobster runtime"
    exit 2
  fi
  baseline_run_id=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("out/evolution")
latest = None
for cand in path.rglob("compare.md"):
    try:
        stat = cand.stat()
    except FileNotFoundError:
        continue
    if latest is None or stat.st_mtime > latest[0]:
        latest = (stat.st_mtime, cand)

if latest is None:
    print("")
    raise SystemExit(0)

text = latest[1].read_text(encoding="utf-8", errors="replace")
baseline = ""
candidate = ""
for line in text.splitlines():
    if line.startswith("Baseline run_id:"):
        baseline = line.split(":", 1)[1].strip()
    if line.startswith("Candidate run_id:"):
        candidate = line.split(":", 1)[1].strip()
print(baseline)
PY
)
  candidate_run_id=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("out/evolution")
latest = None
for cand in path.rglob("compare.md"):
    try:
        stat = cand.stat()
    except FileNotFoundError:
        continue
    if latest is None or stat.st_mtime > latest[0]:
        latest = (stat.st_mtime, cand)

if latest is None:
    print("")
    raise SystemExit(0)

text = latest[1].read_text(encoding="utf-8", errors="replace")
baseline = ""
candidate = ""
for line in text.splitlines():
    if line.startswith("Baseline run_id:"):
        baseline = line.split(":", 1)[1].strip()
    if line.startswith("Candidate run_id:"):
        candidate = line.split(":", 1)[1].strip()
print(candidate)
PY
)
  result_line="compare_md_path=$compare_path baseline_run_id=$baseline_run_id candidate_run_id=$candidate_run_id"
  result_line_path=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path

root = Path("out/evolution/runtime_runs")
latest = None
if root.exists():
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if latest is None or stat.st_mtime > latest[0]:
            latest = (stat.st_mtime, path)
if latest is None:
    print("out/evolution/runtime_runs/last_result_line.txt")
else:
    print(str(latest[1] / "result_line.txt"))
PY
)
  echo "$result_line" > "$result_line_path"
  echo "result_line_path=$result_line_path"
  echo "$result_line"
  exit 0
fi

echo "[demo] baseline -> propose -> approve -> candidate -> compare"

bash scripts/run_baseline_once_mac.sh

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

"$PYTHON_BIN" tools/evolution/summarize_run.py \
  --run-tag baseline \
  --run-dir out/evolution/baseline \
  --repo-root . \
  --output-dir out/evolution/baseline

proposal_path=$("$PYTHON_BIN" tools/evolution/propose.py \
  --baseline-summary out/evolution/baseline/summary.json \
  --output-root out/evolution)

if [ "${EVOLVE_AUTO_APPROVE:-0}" != "1" ]; then
  echo "[approval] 下一步需要人工确认：apply env patch?"
  echo "[proposal] summary (first 10 lines):"
  "$PYTHON_BIN" - "$proposal_path" <<'PY' | head -n 10
import json
import sys
from pathlib import Path

proposal = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lines = []
lines.append(f"proposal_id={proposal.get('proposal_id')}")
lines.append(f"baseline_run_id={proposal.get('baseline_run_id')}")
lines.append("env_patch:")
for key, value in (proposal.get("env_patch") or {}).items():
    lines.append(f"  - {key}={value}")
lines.append(f"rationale={proposal.get('rationale')}")
print("\n".join(lines))
PY
  if [ -t 0 ]; then
    read -r -p "Type APPROVE to continue: " approve_ans
    if [ "$approve_ans" != "APPROVE" ]; then
      echo "[approval] denied by user"
      exit 1
    fi
    export EVOLVE_AUTO_APPROVE=1
  else
    echo "[approval] non-interactive shell. Re-run with EVOLVE_AUTO_APPROVE=1."
    exit 1
  fi
fi

"$PYTHON_BIN" tools/evolution/approval_gate.py --proposal "$proposal_path"

"$PYTHON_BIN" tools/evolution/run_candidate.py \
  --proposal "$proposal_path" \
  --repo-root . \
  --interval 60 \
  --max-loops 1

proposal_dir=$(dirname "$proposal_path")
compare_path=$("$PYTHON_BIN" tools/evolution/compare.py \
  --baseline-summary out/evolution/baseline/summary.json \
  --candidate-summary "${proposal_dir}/summary.json" \
  --proposal "$proposal_path")

baseline_run_id=$("$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
path = Path("out/evolution/baseline/summary.json")
print(json.loads(path.read_text(encoding="utf-8")).get("run_id") or "")
PY
)

candidate_run_id=$("$PYTHON_BIN" - "$proposal_path" <<'PY'
import json
from pathlib import Path
import sys
proposal = Path(sys.argv[1])
summary = proposal.parent / "summary.json"
print(json.loads(summary.read_text(encoding="utf-8")).get("run_id") or "")
PY
)

echo "compare_md_path=$compare_path baseline_run_id=$baseline_run_id candidate_run_id=$candidate_run_id"
