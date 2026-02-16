#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  fi
fi
echo "[guardian] PYTHON_BIN=$PYTHON_BIN"
"$PYTHON_BIN" --version

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] $PYTHON_BIN not found. Please create the repo-local venv first."
  exit 1
fi

mkdir -p logs reports out/guardian

export CHINA_NIGHT_MODE=1
if [ "${ENABLE_LIVE_TRADING:-0}" != "1" ]; then
  export POLY_DRY_RUN=true
  export PAPER_TRADING=1
fi

launcher_module="apps.launcher_demo"
run_mode="${EVOLVE_RUN_MODE:-demo_light}"
if [ "$run_mode" = "real_dryrun" ]; then
  launcher_module="apps.launcher_real_dryrun"
  echo "[guardian] using launcher_real_dryrun"
elif [ "${GUARDIAN_USE_LIVE_LIGHT:-1}" = "1" ] || [ "${EVOLVE_LIVE_LIGHT:-0}" = "1" ] || [ "$run_mode" = "live_light" ]; then
  launcher_module="apps.launcher_live_light"
  echo "[guardian] using launcher_live_light"
fi

"$PYTHON_BIN" tools/evolution/guardian_runner.py \
  --output-root out/guardian \
  --launcher "$launcher_module"
