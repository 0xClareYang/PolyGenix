#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="out/evolution/runtime_probe"
mkdir -p "$OUT_DIR"

{
  echo "== PATH =="
  echo "$PATH"
  echo

  echo "== which/command -v =="
  command -v openclaw || true
  command -v moltbot || true
  command -v clawdbot || true
  command -v claw || true
  command -v lobster || true
  if [ -n "${LOBSTER_BIN:-}" ]; then
    echo "LOBSTER_BIN=$LOBSTER_BIN"
  fi
  if [ -n "${EVOLVE_LOBSTER_PATH:-}" ]; then
    echo "EVOLVE_LOBSTER_PATH=$EVOLVE_LOBSTER_PATH"
  fi
  if [ -f "out/evolution/runtime_probe/lobster_wrapper_path.txt" ]; then
    echo "lobster_wrapper_path_file=$(cat out/evolution/runtime_probe/lobster_wrapper_path.txt)"
  fi
  echo

  echo "== npm diagnostics =="
  if command -v npm >/dev/null 2>&1; then
    npm -v || true
    npm prefix -g || true
    npm bin -g || true
    npm_bin_global="$(npm bin -g 2>/dev/null || true)"
    if [ -n "$npm_bin_global" ] && [ -d "$npm_bin_global" ]; then
      ls -la "$npm_bin_global" | egrep -i "openclaw|moltbot|clawdbot|claw|lobster" || true
    else
      echo "npm bin -g not found or not a directory"
    fi
    npm -g ls --depth=0 | egrep -i "openclaw|moltbot|clawdbot|lobster" || true
  else
    echo "npm not found"
  fi
  echo

  echo "== Spotlight hints =="
  mdfind "kMDItemFSName == 'openclaw' || kMDItemFSName == 'moltbot' || kMDItemFSName == 'clawdbot' || kMDItemFSName == 'claw' || kMDItemFSName == 'lobster'" | head -n 50 || true
  echo

  echo "== versions/help =="
  (claw --version 2>/dev/null || claw -V 2>/dev/null || claw --help 2>/dev/null || true) | head -n 40
  echo
  (lobster --version 2>/dev/null || lobster -V 2>/dev/null || lobster --help 2>/dev/null || true) | head -n 40
  echo
  (claw lobster --help 2>/dev/null || true) | head -n 80
  echo

  echo "== python env hint (if claw installed via pip) =="
  echo "If installed inside .venv, executable may be .venv/bin/claw"
  if [ -x ".venv/bin/claw" ]; then
    echo ".venv/bin/claw exists"
    .venv/bin/claw --help 2>/dev/null | head -n 20 || true
  else
    echo ".venv/bin/claw not found"
  fi

  echo
  echo "== cli_locator (json) =="
  PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
  if [ -x "$PYTHON_BIN" ]; then
    "$PYTHON_BIN" tools/evolution/cli_locator.py --json-out "$OUT_DIR/probe.json" || true
    if [ -f "$OUT_DIR/probe.json" ]; then
      cat "$OUT_DIR/probe.json"
    fi
  else
    echo "PYTHON_BIN not found: $PYTHON_BIN"
  fi
} > "$OUT_DIR/probe_full.txt"

echo "[ok] wrote $OUT_DIR/probe_full.txt"
