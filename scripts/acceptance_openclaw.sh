#!/usr/bin/env bash
set -euo pipefail

echo "=== 0) 基础信息 ==="
pwd
ls -la | head -n 30

echo
echo "=== 1) Repo 完整性快速检查（关键文件必须存在）==="
required_files=(
  "apps/launcher_demo.py"
  "tools/evolution/common.py"
  "tools/evolution/propose.py"
  "tools/evolution/approval_gate.py"
  "tools/evolution/run_candidate.py"
  "tools/evolution/summarize_run.py"
  "tools/evolution/compare.py"
  "scripts/demo_openclaw_evolution.sh"
  "scripts/check_demo_health.sh"
  "workflows/pm_evolution_demo.lobster"
  "docs/openclaw_setup_demo.md"
  "docs/DEMO.md"
)
for f in "${required_files[@]}"; do
  if [ ! -f "$f" ]; then
    echo "[MISSING] $f"
    exit 2
  else
    echo "[OK] $f"
  fi
done

echo
echo "=== 2) Python/venv 验收 ==="
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "[FAIL] python not found (.venv/bin/python or python3)"
    exit 3
  fi
fi
$PYTHON_BIN -V
$PYTHON_BIN -c "import sys; print('python runtime OK', sys.version.split()[0])"

echo
echo "=== 3) Demo Health 自检（应输出 DEMO_HEALTH=OK）==="
./scripts/check_demo_health.sh

echo
echo "=== 3.5) Config Layer Check ==="
if [ ! -f "config/evolution/current.env" ]; then
  echo "[FAIL] config/evolution/current.env missing"
  exit 6
fi
if [ -x "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" - <<'PY'
from tools.evolution.config_store import load_config_layers
cfg = load_config_layers(".")
print(f"[config] merged_keys={len(cfg)}")
PY
fi

echo
echo "=== 3.6) Guardian Dry-Run (short) ==="
set +e
GUARDIAN_MAX_LOOPS=1 EVOLVE_LIVE_LIGHT=0 ./scripts/run_guardian_night.sh
guardian_rc=$?
set -e
guardian_status="OK"
if [ $guardian_rc -ne 0 ]; then
  guardian_status="FAIL"
fi
guardian_health_path="$(ls -t out/guardian/*/health.json 2>/dev/null | head -n 1 || true)"
echo "[guardian] status=$guardian_status health_path=${guardian_health_path:-none}"

echo
echo "=== 3.7) Daily Evolution Dry-Run ==="
set +e
EVOLVE_USE_LOBSTER_RUNTIME=0 EVOLVE_DAILY_MAX_CANDIDATES=1 EVOLVE_DAILY_INTERVAL_SECS=5 ./scripts/run_evolution_daily.sh > /tmp/evolution_daily.out 2>&1
daily_rc=$?
set -e
daily_status="OK"
if [ $daily_rc -ne 0 ]; then
  daily_status="FAIL"
fi
daily_review_path="$(ls -t out/evolution/daily/*/review.md 2>/dev/null | head -n 1 || true)"
echo "[daily] status=$daily_status review_path=${daily_review_path:-none}"

echo
echo "=== 3.8) Rollback Script Check ==="
set +e
./scripts/rollback_to_last_good.sh >/tmp/rollback.out 2>&1
rollback_rc=$?
set -e
rollback_status="OK"
if [ $rollback_rc -ne 0 ]; then
  rollback_status="FAIL"
fi
echo "[rollback] status=$rollback_status"

echo
echo "=== 4) 关键：Human-in-the-loop 演示（自动审批版本）==="
echo "期望：最后一行固定输出 compare_md_path=... baseline_run_id=... candidate_run_id=..."
EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh | tee /tmp/demo_openclaw_evolution.out

echo
echo "=== 5) 解析 demo 输出的关键字段（compare 路径 + run_id）==="
last_line="$(tail -n 1 /tmp/demo_openclaw_evolution.out || true)"
echo "LAST_LINE=$last_line"
compare_path=""
baseline_run_id=""
candidate_run_id=""
if [ -x "$PYTHON_BIN" ]; then
  read -r compare_path baseline_run_id candidate_run_id < <("$PYTHON_BIN" tools/evolution/acceptance_parse.py --file /tmp/demo_openclaw_evolution.out --fields)
fi
if [ -z "$compare_path" ] && [ -x "$PYTHON_BIN" ]; then
  read -r compare_path baseline_run_id candidate_run_id < <("$PYTHON_BIN" - <<'PY'
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
if not latest:
    print("", "", "")
else:
    text = latest[1].read_text(encoding="utf-8", errors="replace")
    base = ""
    cand = ""
    for line in text.splitlines():
        if line.startswith("Baseline run_id:"):
            base = line.split(":", 1)[1].strip()
        if line.startswith("Candidate run_id:"):
            cand = line.split(":", 1)[1].strip()
    print(str(latest[1]), base, cand)
PY
)
fi
echo "compare_path=$compare_path"
echo "baseline_run_id=$baseline_run_id"
echo "candidate_run_id=$candidate_run_id"

if [ -z "$compare_path" ] || [ ! -f "$compare_path" ]; then
  echo "[FAIL] compare.md 未生成或路径解析失败"
  exit 4
fi
if [ -z "$baseline_run_id" ] || [ -z "$candidate_run_id" ]; then
  echo "[FAIL] baseline/candidate run_id 为空"
  exit 5
fi
echo "[OK] compare.md & run_id 均有效"

echo
echo "=== 6) 展示 compare.md 关键内容（评委最关心的 3 段）==="
sed -n '1,60p' "$compare_path"
echo
grep -n "## Demo Verdict" -A25 "$compare_path" || true
echo
grep -n "## Safety" -A20 "$compare_path" || true

echo
echo "=== 7) OpenClaw/Lobster Runtime 探测（不强行安装）==="
if [ -x "scripts/probe_openclaw_runtime.sh" ]; then
  ./scripts/probe_openclaw_runtime.sh
  echo "[probe] wrote out/evolution/runtime_probe/probe_full.txt"
fi

RUNTIME_CLI_NAME="missing"
RUNTIME_CLI_PATH="none"
LOBSTER_CLI_MODE="missing"
LOBSTER_CLI_PATH="none"

if [ -x "$PYTHON_BIN" ]; then
  IFS=$'\t' read -r RUNTIME_CLI_NAME RUNTIME_CLI_PATH LOBSTER_CLI_MODE LOBSTER_CLI_PATH < <("$PYTHON_BIN" - <<'PY'
from tools.evolution.cli_locator import locate_cli

data = locate_cli()
runtime_name = data.get("runtime_cli_name") or "missing"
runtime_path = data.get("runtime_cli_path") or "none"
lobster_mode = data.get("lobster_mode") or "missing"
lobster_path = data.get("lobster_path") or "none"
print(f"{runtime_name}\t{runtime_path}\t{lobster_mode}\t{lobster_path}")
PY
)
fi

echo "runtime_cli=$RUNTIME_CLI_NAME runtime_cli_path=$RUNTIME_CLI_PATH"
echo "lobster_cli=$LOBSTER_CLI_MODE lobster_cli_path=$LOBSTER_CLI_PATH"

if [ "$RUNTIME_CLI_NAME" != "missing" ]; then
  echo "[runtime] $RUNTIME_CLI_NAME help:"
  "$RUNTIME_CLI_PATH" --help 2>/dev/null | head -n 30 || true
fi
if [ "$LOBSTER_CLI_MODE" = "standalone" ]; then
  echo "[lobster] help:"
  "$LOBSTER_CLI_PATH" --help 2>/dev/null | head -n 30 || true
elif [ "$LOBSTER_CLI_MODE" = "subcommand" ]; then
  echo "[lobster] subcommand help:"
  "$LOBSTER_CLI_PATH" lobster --help 2>/dev/null | head -n 30 || true
fi

echo
echo "=== 8) Runtime-level 演示（可选：需 CLI 齐全）==="
RUNTIME_DEMO_STATUS="demo-only"
RUNTIME_DEMO_REASON="missing_cli"
if [ "$RUNTIME_CLI_NAME" != "missing" ] && [ "$LOBSTER_CLI_MODE" != "missing" ]; then
  echo "[runtime] running minimal lobster runtime check ..."
  set +e
  ./scripts/demo_lobster_runtime_min.sh
  min_rc=$?
  set -e
  if [ $min_rc -ne 0 ]; then
    RUNTIME_DEMO_STATUS="failed"
    RUNTIME_DEMO_REASON="min_runtime_failed"
  else
    echo "[runtime] attempting EVOLVE_USE_LOBSTER_RUNTIME=1 full demo ..."
    if [ "$LOBSTER_CLI_MODE" = "standalone" ] && [ "$LOBSTER_CLI_PATH" != "none" ]; then
      export EVOLVE_LOBSTER_PATH="$LOBSTER_CLI_PATH"
    fi
    set +e
    EVOLVE_USE_LOBSTER_RUNTIME=1 EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh | tee /tmp/demo_openclaw_evolution_runtime.out
    runtime_rc=$?
    set -e
    if [ $runtime_rc -eq 0 ]; then
      runtime_result_line_path="$(grep -E 'result_line_path=' /tmp/demo_openclaw_evolution_runtime.out | tail -n 1 | sed -n 's/.*result_line_path=\\([^ ]*\\).*/\\1/p')"
      if [ -x "$PYTHON_BIN" ]; then
        read -r runtime_compare_path runtime_baseline_run_id runtime_candidate_run_id < <("$PYTHON_BIN" tools/evolution/acceptance_parse.py --file /tmp/demo_openclaw_evolution_runtime.out --fields)
      fi
      if [ -z "$runtime_compare_path" ] && [ -x "$PYTHON_BIN" ]; then
        read -r runtime_compare_path runtime_baseline_run_id runtime_candidate_run_id < <("$PYTHON_BIN" - <<'PY'
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
if not latest:
    print("", "", "")
else:
    text = latest[1].read_text(encoding="utf-8", errors="replace")
    base = ""
    cand = ""
    for line in text.splitlines():
        if line.startswith("Baseline run_id:"):
            base = line.split(":", 1)[1].strip()
        if line.startswith("Candidate run_id:"):
            cand = line.split(":", 1)[1].strip()
    print(str(latest[1]), base, cand)
PY
)
      fi
      if [ -n "$runtime_compare_path" ] && [ -n "$runtime_baseline_run_id" ] && [ -n "$runtime_candidate_run_id" ]; then
        RUNTIME_DEMO_STATUS="runtime-ok"
        RUNTIME_DEMO_REASON="runtime_run_success"
        echo "[runtime] compare_md_path=$runtime_compare_path baseline_run_id=$runtime_baseline_run_id candidate_run_id=$runtime_candidate_run_id"
      else
        RUNTIME_DEMO_STATUS="failed"
        RUNTIME_DEMO_REASON="runtime_compare_missing"
      fi
    else
      RUNTIME_DEMO_STATUS="failed"
      RUNTIME_DEMO_REASON="runtime_run_failed"
    fi
  fi
else
  echo "[runtime] demo-style only: runtime_cli or lobster_cli missing."
fi

mode="demo"
if [ "${EVOLVE_LIVE_LIGHT:-0}" = "1" ]; then
  mode="live_light"
fi
if [ "$RUNTIME_DEMO_STATUS" = "runtime-ok" ]; then
  mode="runtime"
fi

final_compare_path="$compare_path"
final_baseline_run_id="$baseline_run_id"
final_candidate_run_id="$candidate_run_id"
if [ "$mode" = "runtime" ] && [ -n "${runtime_compare_path:-}" ] && [ -n "${runtime_baseline_run_id:-}" ] && [ -n "${runtime_candidate_run_id:-}" ]; then
  final_compare_path="$runtime_compare_path"
  final_baseline_run_id="$runtime_baseline_run_id"
  final_candidate_run_id="$runtime_candidate_run_id"
fi

best_score=""
current_score=""
adopt_status=""
failure_streak=""
frozen=""
if [ -x "$PYTHON_BIN" ]; then
  read -r best_score failure_streak frozen < <("$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

path = Path("out/evolution/state.json")
if not path.exists():
    print("", "", "")
    raise SystemExit(0)
data = json.loads(path.read_text(encoding="utf-8"))
best = data.get("best_score")
streak = data.get("failure_streak")
frozen = data.get("frozen")
print("" if best is None else best, "" if streak is None else streak, "" if frozen is None else frozen)
PY
)
  if [ -n "$final_compare_path" ]; then
    compare_json="${final_compare_path%/compare.md}/compare.json"
    if [ -f "$compare_json" ]; then
      read -r current_score adopt_status < <("$PYTHON_BIN" - <<'PY' "$compare_json"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
fitness = data.get("fitness") or {}
score = fitness.get("candidate_score")
adopt = fitness.get("adopt")
print("" if score is None else score, "" if adopt is None else adopt)
PY
)
    fi
  fi
fi

echo
echo "=== 9) 最终验收口径输出（可直接发给评委）==="
echo "ACCEPTANCE:"
echo "- demo_health=OK (if step3 passed)"
echo "- baseline_run_id=$final_baseline_run_id"
echo "- candidate_run_id=$final_candidate_run_id"
echo "- compare_md_path=$final_compare_path"
echo "- runtime_cli=$RUNTIME_CLI_NAME"
echo "- runtime_cli_path=$RUNTIME_CLI_PATH"
echo "- lobster_cli=$LOBSTER_CLI_MODE"
echo "- lobster_cli_path=$LOBSTER_CLI_PATH"
echo "- mode=$mode"
echo "- runtime_demo_status=$RUNTIME_DEMO_STATUS"
echo "- runtime_demo_reason=$RUNTIME_DEMO_REASON"
echo "- best_score=$best_score"
echo "- current_score=$current_score"
echo "- adopt_status=$adopt_status"
echo "- failure_streak=$failure_streak"
echo "- frozen=$frozen"
echo "- guardian_status=${guardian_status:-unknown}"
echo "- daily_evolution_status=${daily_status:-unknown}"
echo "- current_env_path=config/evolution/current.env"
echo "- last_good_env_path=config/evolution/last_good.env"
echo "DONE"
