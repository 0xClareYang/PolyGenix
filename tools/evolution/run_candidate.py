from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import run_subprocess, safe_load_json
from tools.evolution.summarize_run import summarize_run


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    run_mode = os.environ.get("EVOLVE_RUN_MODE")
    if run_mode:
        env["EVOLVE_RUN_MODE"] = run_mode
    env.update(
        {
            "PYTHONPATH": "src",
            "RUNNER_FETCH_MODE": "light",
            "POLY_DRY_RUN": "true",
            "PAPER_TRADING": "1",
            "ONE_LOOP": "1",
            "SKIP_FETCH_PREFLIGHT": "1",
            "SERVICE_REST_MAX_CONCURRENCY": "1",
            "SERVICE_REST_RATE_LIMIT_PER_SEC": "0.3",
            "NEWS_FORCE_REFRESH": "0",
            "NEWS_BOOTSTRAP_TTL_SECS": "600",
            "NEWS_BOOTSTRAP_TIMEOUT_SECS": "30",
        }
    )
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run candidate with env patch.")
    parser.add_argument("--proposal", required=True, help="Path to proposal.json")
    parser.add_argument("--repo-root", default=".", help="Repo root")
    parser.add_argument("--interval", default="60", help="Trade loop interval")
    parser.add_argument("--max-loops", default="1", help="Max loops")
    args = parser.parse_args()

    proposal_path = Path(args.proposal)
    proposal = safe_load_json(proposal_path)
    if proposal is None:
        print(f"[error] proposal not found: {proposal_path}")
        return 1

    proposal_id = proposal.get("proposal_id")
    if not proposal_id:
        print("[error] proposal_id missing")
        return 1

    repo_root = Path(args.repo_root)
    output_dir = Path("out") / "evolution" / proposal_id
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _base_env()
    env_patch = proposal.get("env_patch", {})
    for key, value in env_patch.items():
        env[str(key)] = str(value)

    optional_patch = proposal.get("optional_env_patch", {})
    for key, payload in optional_patch.items():
        if isinstance(payload, dict) and payload.get("enabled") is True:
            env[str(key)] = str(payload.get("value"))

    python_bin = os.environ.get("PYTHON_BIN", str(repo_root / ".venv" / "bin" / "python"))
    if not Path(python_bin).exists():
        python_bin = sys.executable
    run_mode = os.environ.get("EVOLVE_RUN_MODE", "demo_light").strip().lower()
    launcher_module = "apps.launcher_demo"
    if run_mode == "real_dryrun":
        launcher_module = "apps.launcher_real_dryrun"
    elif run_mode == "live_light" or os.environ.get("EVOLVE_LIVE_LIGHT") == "1":
        launcher_module = "apps.launcher_live_light"

    cmd = [
        python_bin,
        "-u",
        "-m",
        launcher_module,
        "trade",
        "--interval",
        str(args.interval),
        "--log-level",
        "INFO",
        "--max-loops",
        str(args.max_loops),
    ]

    stdout_path = output_dir / "candidate_stdout.log"
    stderr_path = output_dir / "candidate_stderr.log"

    exit_code = run_subprocess(cmd, env, stdout_path, stderr_path)
    summarize_run(
        run_tag="candidate",
        run_dir=output_dir,
        repo_root=repo_root,
        output_dir=output_dir,
    )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
