name: pm-evolution-demo
steps:
  - id: baseline
    command: EVOLVE_RUN_MODE=${EVOLVE_RUN_MODE:-demo_light} bash scripts/run_baseline_once_mac.sh
  - id: summarize
    command: .venv/bin/python tools/evolution/summarize_run.py --run-tag baseline --run-dir out/evolution/baseline --repo-root . --output-dir out/evolution/baseline
  - id: propose
    command: .venv/bin/python tools/evolution/propose.py --baseline-summary out/evolution/baseline/summary.json --output-root out/evolution
  - id: proposal_path
    command: "printf '%s' \"$propose.stdout\" | tr -d '\\n'"
  - id: approval
    command: cat "$proposal_path.stdout"
    approval: required
  - id: proposal_dir
    command: "dirname \"$proposal_path.stdout\" | tr -d '\\n'"
  - id: candidate
    command: EVOLVE_RUN_MODE=${EVOLVE_RUN_MODE:-demo_light} .venv/bin/python tools/evolution/run_candidate.py --proposal "$proposal_path.stdout" --repo-root . --interval 60 --max-loops 1
    condition: $approval.approved
  - id: compare
    command: .venv/bin/python tools/evolution/compare.py --baseline-summary out/evolution/baseline/summary.json --candidate-summary "$proposal_dir.stdout/summary.json" --proposal "$proposal_path.stdout"
    condition: $approval.approved
