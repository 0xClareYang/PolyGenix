# Monad Testnet Deployment

This repo includes a minimal proof contract:

- `chain/monad/src/PolyGenixAnchor.sol`

It publishes immutable submission metadata on-chain:

- `projectName`
- `releaseTag`
- `deployer`
- `deployedAt`

## 1) Prerequisites

- Foundry installed (`forge`, `cast`)
- A dedicated test wallet private key (testnet only)
- Monad testnet balance for deployment gas

## 2) Wallet Preflight (recommended)

Before deploy, verify wallet address + balance:

```bash
export MONAD_RPC_URL=https://testnet-rpc.monad.xyz
export MONAD_PRIVATE_KEY=<your_private_key_hex>
./scripts/check_monad_wallet.sh
```

Outputs:

- `out/chain/monad_wallet_status.txt`

If balance is zero, fund the address first via Monad testnet faucet, then retry.

## 3) Deploy

```bash
export MONAD_PRIVATE_KEY=<your_private_key_hex>
export MONAD_RPC_URL=https://testnet-rpc.monad.xyz
export PROJECT_NAME=PolyGenix
export RELEASE_TAG=moltiverse-2026
export DEPLOY_RETRIES=5
export DEPLOY_RETRY_SLEEP_SECS=5

./scripts/deploy_monad_testnet.sh
```

Outputs:

- `out/chain/monad_latest.env`
- `out/chain/monad_deploy_*.log`

## 4) Verify Read Methods

```bash
source out/chain/monad_latest.env
cast call "$contract_address" "projectName()(string)" --rpc-url "$MONAD_RPC_URL"
cast call "$contract_address" "releaseTag()(string)" --rpc-url "$MONAD_RPC_URL"
```

## 5) Common Errors

- `Failed to decode private key`
  - Your `MONAD_PRIVATE_KEY` is not a raw 64-hex (or `0x` + 64-hex) value.
- `Signer had insufficient balance`
  - Wallet is valid but lacks testnet gas. Fund the deployer address first.
- `Connection reset by peer`
  - Temporary network instability to RPC endpoint. Retry with `DEPLOY_RETRIES` or switch network.

## 6) Security Rules

- Never commit private keys, mnemonics, or wallet JSON.
- Use a dedicated test wallet for hackathon demo.
- Keep deployment logs public-safe; redact any accidental secrets before sharing.
