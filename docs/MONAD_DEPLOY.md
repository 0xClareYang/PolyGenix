# Monad Testnet Deployment (Competition Proof)

This repo includes a minimal contract under `chain/monad/src/PolyGenixAnchor.sol`.

The purpose is to provide a public on-chain anchor for the submission:
- `projectName`
- `releaseTag`
- `deployer`
- `deployedAt`

## Prerequisites

- Foundry installed (`forge`, `cast`)
- A wallet private key with testnet funds

## Deploy

```bash
export MONAD_PRIVATE_KEY=<your_private_key_hex>
export MONAD_RPC_URL=https://testnet-rpc.monad.xyz
export PROJECT_NAME=PolyGenix
export RELEASE_TAG=moltiverse-2026

./scripts/deploy_monad_testnet.sh
```

The script writes:
- `out/chain/monad_latest.env`
- `out/chain/monad_deploy_*.log`

## Safety

- Never commit private keys.
- Use testnet funds only.
