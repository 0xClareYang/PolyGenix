#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONAD_DIR="$REPO_ROOT/chain/monad"

MONAD_RPC_URL="${MONAD_RPC_URL:-https://testnet-rpc.monad.xyz}"
PROJECT_NAME="${PROJECT_NAME:-PolyGenix}"
RELEASE_TAG="${RELEASE_TAG:-moltiverse-2026}"
DEPLOY_RETRIES="${DEPLOY_RETRIES:-3}"
DEPLOY_RETRY_SLEEP_SECS="${DEPLOY_RETRY_SLEEP_SECS:-4}"

if ! command -v forge >/dev/null 2>&1; then
  echo "[error] forge not found. Install Foundry first: https://book.getfoundry.sh/getting-started/installation" >&2
  exit 1
fi

if [[ -z "${MONAD_PRIVATE_KEY:-}" ]]; then
  echo "[error] MONAD_PRIVATE_KEY is required (hex private key, do not commit)." >&2
  exit 2
fi

mkdir -p "$REPO_ROOT/out/chain"
LOG_PATH="$REPO_ROOT/out/chain/monad_deploy_$(date +%Y%m%d_%H%M%S).log"

cd "$MONAD_DIR"

echo "[info] deploying PolyGenixAnchor to Monad testnet"
echo "[info] rpc=$MONAD_RPC_URL"
echo "[info] project_name=$PROJECT_NAME release_tag=$RELEASE_TAG"
echo "[info] retries=$DEPLOY_RETRIES retry_sleep_secs=$DEPLOY_RETRY_SLEEP_SECS"

if ! cast chain-id --rpc-url "$MONAD_RPC_URL" >/dev/null 2>&1; then
  echo "[error] rpc unreachable: $MONAD_RPC_URL" >&2
  exit 4
fi

deploy_output=""
deploy_ok=0
for ((attempt=1; attempt<=DEPLOY_RETRIES; attempt++)); do
  echo "[info] deploy_attempt=$attempt/$DEPLOY_RETRIES" | tee -a "$LOG_PATH"

  set +e
  attempt_output="$(forge create src/PolyGenixAnchor.sol:PolyGenixAnchor \
    --broadcast \
    --rpc-url "$MONAD_RPC_URL" \
    --private-key "$MONAD_PRIVATE_KEY" \
    --constructor-args "$PROJECT_NAME" "$RELEASE_TAG" 2>&1)"
  attempt_code=$?
  set -e

  printf "%s\n" "$attempt_output" | tee -a "$LOG_PATH"

  if [[ $attempt_code -eq 0 ]]; then
    deploy_ok=1
    deploy_output="$attempt_output"
    break
  fi

  if printf "%s\n" "$attempt_output" | rg -q "Failed to decode private key"; then
    echo "[error] MONAD_PRIVATE_KEY format invalid." >&2
    exit 5
  fi

  if [[ $attempt -lt $DEPLOY_RETRIES ]]; then
    echo "[warn] attempt failed, retrying in ${DEPLOY_RETRY_SLEEP_SECS}s..." | tee -a "$LOG_PATH"
    sleep "$DEPLOY_RETRY_SLEEP_SECS"
  fi
done

if [[ $deploy_ok -ne 1 ]]; then
  echo "[error] deployment failed after $DEPLOY_RETRIES attempts." >&2
  echo "[error] inspect log: $LOG_PATH" >&2
  exit 6
fi

contract_address="$(sed -n 's/^Deployed to: \(0x[a-fA-F0-9]\{40\}\)$/\1/p' "$LOG_PATH" | tail -n 1)"
if [[ -z "$contract_address" ]]; then
  contract_address="$(printf "%s\n" "$deploy_output" | sed -n 's/^Deployed to: \(0x[a-fA-F0-9]\{40\}\)$/\1/p' | tail -n 1)"
fi

if [[ -z "$contract_address" ]]; then
  echo "[error] deployment finished but contract address could not be parsed." >&2
  echo "[error] inspect log: $LOG_PATH" >&2
  exit 3
fi

echo "[ok] contract_address=$contract_address"
echo "[ok] deploy_log=$LOG_PATH"

echo "contract_address=$contract_address" > "$REPO_ROOT/out/chain/monad_latest.env"
echo "deploy_log=$LOG_PATH" >> "$REPO_ROOT/out/chain/monad_latest.env"

echo "[info] verify read methods"
cast call "$contract_address" "projectName()(string)" --rpc-url "$MONAD_RPC_URL" || true
cast call "$contract_address" "releaseTag()(string)" --rpc-url "$MONAD_RPC_URL" || true
