# PolyGenix

**PolyGenix** is a human-in-the-loop evolution framework for prediction-market trading agents.

This public competition edition focuses on one core capability:

- **safe autonomous iteration**: `baseline -> proposal -> approval -> candidate -> compare`

It is designed for stage demos and reproducible evaluation, with explicit safety gates and deterministic artifacts.

## Why This Project

Prediction-market agents fail in production for two recurring reasons:

- strategy changes are hard to audit and compare objectively
- automation without approval gates creates operational risk

PolyGenix solves this by combining:

- **agent-generated config proposals**
- **mandatory human approval**
- **A/B run comparison with fitness scoring**
- **stateful adopt/reject logic with rollback/freeze controls**

## What Is Included in Public Repo

- OpenClaw/Lobster-compatible runtime orchestration hooks
- Evolution tools (`tools/evolution/*`)
- Demo launcher and acceptance scripts
- Guardian + daily evolution scheduling scripts
- Monad testnet deployment scaffold for on-chain submission proof

## What Is Intentionally Not Open-Sourced

- proprietary alpha models
- private risk knobs used in production
- credentials, infra secrets, private endpoints

## Safety Model (Default Fail-Closed)

- dry-run + paper mode by default
- approval gate required unless explicitly bypassed (`EVOLVE_AUTO_APPROVE=1`)
- security redaction helpers for logs and reports
- no private keys committed to repository

## End-to-End Flow

```text
Baseline Run
  -> Summarize Metrics
  -> Generate Proposal (env patch)
  -> Human Approval Gate
  -> Candidate Run
  -> Compare + Fitness + Adopt/Reject
```

Key artifacts are always written under:

- `out/evolution/`
- `logs/`
- `reports/`

## Repository Layout

- `apps/launcher_demo.py`: demo launcher used for reproducible local runs
- `tools/evolution/`: proposal, approval, summarize, compare, fitness, state management
- `scripts/demo_openclaw_evolution.sh`: one-command stage demo
- `scripts/acceptance_openclaw.sh`: integration acceptance script
- `scripts/run_guardian_night.sh`: guardian runner
- `scripts/run_evolution_daily.sh`: daily batch evolution driver
- `workflows/pm_evolution_demo.lobster`: workflow skeleton for Lobster runtime
- `chain/monad/`: minimal Monad deployment contract + foundry config

## Quick Start

### 1) Python environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

### 2) Health check

```bash
./scripts/check_demo_health.sh
```

Expected:

- `DEMO_HEALTH=OK`

### 3) Run full human-in-the-loop demo

```bash
EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh
```

Expected last line:

```text
compare_md_path=... baseline_run_id=... candidate_run_id=...
```

### 4) Open acceptance suite

```bash
EVOLVE_AUTO_APPROVE=1 ./scripts/acceptance_openclaw.sh
```

## OpenClaw / Lobster Runtime Mode

If runtime CLI is available, you can run runtime-level orchestration:

```bash
./scripts/probe_openclaw_runtime.sh
EVOLVE_USE_LOBSTER_RUNTIME=1 EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh
```

Runtime detection supports:

- standalone `lobster`
- runtime subcommand style (`claw ...`, `clawdbot ...`, etc.)

See `docs/openclaw_setup_demo.md` for CLI mapping and troubleshooting.

## Monad Testnet Deployment (Submission Proof)

A minimal on-chain anchor contract is included at:

- `chain/monad/src/PolyGenixAnchor.sol`

### Wallet preflight

```bash
export MONAD_RPC_URL=https://testnet-rpc.monad.xyz
export MONAD_PRIVATE_KEY=<your_private_key_hex>
./scripts/check_monad_wallet.sh
```

### Deploy

```bash
export MONAD_RPC_URL=https://testnet-rpc.monad.xyz
export MONAD_PRIVATE_KEY=<your_private_key_hex>
export PROJECT_NAME=PolyGenix
export RELEASE_TAG=moltiverse-2026
./scripts/deploy_monad_testnet.sh
```

Deployment outputs:

- `out/chain/monad_latest.env`
- `out/chain/monad_deploy_*.log`

Detailed guide:

- `docs/MONAD_DEPLOY.md`

## Guardian + Daily Evolution Ops

- night guardian (stability-first):

```bash
./scripts/run_guardian_night.sh
```

- daily batch evolution:

```bash
./scripts/run_evolution_daily.sh
```

- daytime review pack:

```bash
./scripts/review_daytime_pack.sh
```

## Competition Demo Checklist

Before submission/demo recording:

1. run `./scripts/check_demo_health.sh`
2. run `EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh`
3. capture latest `compare.md`
4. (optional) run runtime mode with Lobster CLI
5. deploy Monad anchor and record contract address

## Judge-Facing Value Map

- Innovation: human approval is embedded directly in the evolution loop, not bolted on.
- Technical depth: runtime-aware orchestration (demo mode + Lobster runtime mode), stateful fitness/adopt logic, guardian + daily loops.
- Practical safety: dry-run defaults, explicit redaction, rollback/freeze mechanisms.
- Reproducibility: deterministic artifact outputs and acceptance scripts for quick re-runs.

## Security Notes

- Never paste private keys into committed files.
- Never upload `.env`, wallet files, or secret snapshots.
- Treat third-party skills/extensions as untrusted by default.

See:

- `docs/SECURITY_NOTES.md`

## License

MIT (see `LICENSE`).
