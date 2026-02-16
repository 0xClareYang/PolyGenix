# PolyGenix Evolution Agent (Competition Public Edition)

This repo is the public submission package for the Moltiverse-style agent track.

## What This Repo Demonstrates

- Human-in-the-loop strategy evolution:
  - baseline -> proposal -> approval gate -> candidate -> compare report
- OpenClaw/Lobster runtime probing and optional runtime execution path
- Guardian + daily evolution orchestration (safe defaults)
- Deterministic artifact outputs under `out/`, `logs/`, `reports/`

## What Is Intentionally Removed

- Proprietary production strategy code
- Private alpha/risk parameter sets
- API keys, secrets, infra endpoints, and any credential material

## Safety Guarantees

- Default mode is paper + dry-run
- No real orders are submitted in the included demo workflows
- Approval gate is required unless `EVOLVE_AUTO_APPROVE=1` is set explicitly

## Quick Start (macOS / Linux)

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip pytest
./scripts/check_demo_health.sh
EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh
```

## Runtime Probe

```bash
./scripts/probe_openclaw_runtime.sh
```

## Key Docs

- `docs/DEMO.md`: on-stage demo flow
- `docs/openclaw_setup_demo.md`: OpenClaw/Lobster runtime setup
- `docs/SECURITY_NOTES.md`: security and redaction guidance

