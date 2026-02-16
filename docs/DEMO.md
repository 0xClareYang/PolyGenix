# OpenClaw Human-in-the-loop Evolution Demo (2-day contest)

## What you will show
- A safe, human-in-the-loop evolution loop driven by OpenClaw/Lobster:
  - baseline -> proposal -> approval -> candidate -> compare
- Safety: changes are gated by approval; resume token can continue without re-running earlier steps.
- This demo is **dry-run + paper only** and does not submit real orders.

## Live script (stage narration)

1) Baseline does
- Pulls a light universe, evaluates signals, and logs funnel + loop metrics.
- Writes `logs/polymarket.log` and `reports/pipeline_status.json`.

2) Agent proposes
- Generates an env patch (REST stability + demo strategy params).
- Shows the diff and explains why these changes might improve signal throughput.

3) Human approval
- You decide whether to apply the patch.
- After approval, candidate runs and `compare.md` summarizes the outcome.

## 3 commands for the live demo

1) Install/check deps
```
./scripts/setup_dev_mac.sh
```

2) Run the demo loop (auto-approve for stage)
```
EVOLVE_AUTO_APPROVE=1 ./scripts/demo_openclaw_evolution.sh
```

3) Open the latest compare report
```
cat "$(ls -t out/evolution/*/compare.md | head -n 1)"
```

## Notes
- The demo uses `apps/launcher_demo.py` to avoid `polymarket.data` dependency.
- All output is written under `out/` and `logs/` and is safe to share.
