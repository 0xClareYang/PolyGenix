#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  fi
fi
echo "[health] PYTHON_BIN=$PYTHON_BIN"
"$PYTHON_BIN" --version

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[health] missing python at $PYTHON_BIN"
  exit 1
fi

mkdir -p logs reports out

# write checks
health_tmp="out/.healthcheck"
echo "ok" > "$health_tmp"
rm -f "$health_tmp"

echo "[health] python runtime check"
"$PYTHON_BIN" -c "import sys; print('python runtime OK', sys.version.split()[0])"

echo "[health] pytest evolution smoke"
if ! "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pip install pytest >/dev/null 2>&1 || true
fi
"$PYTHON_BIN" -m pytest -q tests/test_evolution_smoke.py

echo "DEMO_HEALTH=OK"
