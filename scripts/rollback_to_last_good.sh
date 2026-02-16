#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cfg_dir="config/evolution"
current_env="$cfg_dir/current.env"
last_good_env="$cfg_dir/last_good.env"

if [ ! -f "$last_good_env" ]; then
  echo "[error] last_good.env not found at $last_good_env"
  exit 1
fi

mkdir -p out/evolution/rollbacks
ts="$(date +%Y%m%d_%H%M%S)"
out_dir="out/evolution/rollbacks/$ts"
mkdir -p "$out_dir"

cp "$last_good_env" "$current_env"

cat > "$out_dir/rollback.md" <<EOF
# Rollback Performed

- time: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- source: $last_good_env
- target: $current_env
EOF

echo "[rollback] wrote $out_dir/rollback.md"
