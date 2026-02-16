# OpenClaw Demo Setup (Manual)

This repo ships a manual, optional OpenClaw demo integration. It is **not required** for the baseline evolution loop.

## Install (manual)

- Install OpenClaw using your preferred internal method.
- Ensure the CLI is available on `PATH`.
  - Some installs expose `claw` (recommended), others expose `openclaw` (legacy), and some provide `lobster` directly.
- Confirm you can run one of these:
  - `claw --help`
  - `claw lobster --help`
  - `openclaw --help`
  - `lobster --help`

## CLI name may be `claw`

Quick detection commands:
- `command -v claw`
- `claw --help`
- `claw lobster --help`
- `command -v lobster`

## CLI naming map (historical)

| Release era | Typical binary |
| --- | --- |
| older | `clawdbot` |
| mid | `moltbot` |
| newer | `openclaw` or `claw` |

## Confirm install (runtime prerequisites)

- Check PATH resolution:
  - `command -v clawdbot`
  - `command -v moltbot`
  - `command -v openclaw`
  - `command -v claw`
  - `command -v lobster`
- If installed via npm:
  - `npm prefix -g`
  - `npm bin -g`

## Lobster requirement

- A Lobster CLI must be available either as:
  - standalone `lobster` binary in `PATH`, or
  - a subcommand exposed by your runtime CLI (e.g., `claw lobster --help`).
- Use `--help` output to discover the exact run/resume commands for your version.
- If `~/.local/bin` is not on `PATH`, the demo scripts still work by calling the resolved absolute `lobster` path.

## Run the workflow (template)

> The exact subcommand/flags depend on your OpenClaw version. Use this template and replace `<...>` with your actual CLI.
> If your CLI binary is `claw`, substitute `claw` for `openclaw` below.

- Run:
  - `openclaw <run-subcommand> workflows/pm_evolution_demo.lobster`
- You should see the workflow pause at the approval step and return a `resumeToken`.

## Resume after approval (template)

- Resume with approval:
  - `openclaw <resume-subcommand> --resume-token <token> --approve true`

## Common pitfalls

- If the workflow cannot find Python, export `PYTHON_BIN=.venv/bin/python` before running.
- If you run in a non-interactive shell, use `EVOLVE_AUTO_APPROVE=1` for the local demo gate.
- Ensure `logs/` and `reports/` are writable (the demo writes to both).

## Notes

- Do not store secrets in workflow files.
- The demo loop uses `POLY_DRY_RUN=true` and `PAPER_TRADING=1` by default.
- The approval gate is implemented in `tools/evolution/approval_gate.py` for local demo parity.
- Do not blindly install third-party skills or plugins; review the code before enabling.
- Extensions/skills can execute code with your user permissions. Only enable trusted sources and run workflows from this repo directory.
