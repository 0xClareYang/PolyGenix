#!/usr/bin/env bash
set -euo pipefail

MONAD_RPC_URL="${MONAD_RPC_URL:-https://testnet-rpc.monad.xyz}"
MONAD_DEPLOYER_ADDRESS="${MONAD_DEPLOYER_ADDRESS:-}"

if ! command -v cast >/dev/null 2>&1; then
  echo "[error] cast not found. Install Foundry first: https://book.getfoundry.sh/getting-started/installation" >&2
  exit 1
fi

if [ -n "${MONAD_PRIVATE_KEY:-}" ]; then
  MONAD_DEPLOYER_ADDRESS="$(cast wallet address --private-key "$MONAD_PRIVATE_KEY" 2>/dev/null || true)"
fi

if [ -z "$MONAD_DEPLOYER_ADDRESS" ]; then
  echo "[error] set MONAD_PRIVATE_KEY or MONAD_DEPLOYER_ADDRESS." >&2
  exit 2
fi

chain_id="$(cast chain-id --rpc-url "$MONAD_RPC_URL")"
balance_wei="$(cast balance "$MONAD_DEPLOYER_ADDRESS" --rpc-url "$MONAD_RPC_URL")"
balance_eth="$(cast to-unit "$balance_wei" ether 2>/dev/null || echo unknown)"

mkdir -p out/chain
cat > out/chain/monad_wallet_status.txt <<STATUS
rpc_url=$MONAD_RPC_URL
chain_id=$chain_id
deployer_address=$MONAD_DEPLOYER_ADDRESS
balance_wei=$balance_wei
balance_eth=$balance_eth
STATUS

echo "[ok] rpc_url=$MONAD_RPC_URL"
echo "[ok] chain_id=$chain_id"
echo "[ok] deployer_address=$MONAD_DEPLOYER_ADDRESS"
echo "[ok] balance_wei=$balance_wei"
echo "[ok] balance_eth=$balance_eth"
echo "[ok] status_file=out/chain/monad_wallet_status.txt"

if [ "$balance_wei" = "0" ]; then
  echo "[warn] zero balance. Fund this address from Monad testnet faucet before deploy."
fi
