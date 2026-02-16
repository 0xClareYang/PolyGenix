from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import ensure_dir, run_subprocess, write_json
from tools.evolution.compare import compute_fitness
from tools.evolution.config_store import (
    load_config_layers,
    load_env_file,
    promote_candidate,
    sync_from_state_json,
)
from tools.evolution.summarize_run import summarize_run
from tools.evolution.cli_locator import locate_cli

CN_TZ = timezone(timedelta(hours=8))


def _china_date() -> str:
    return datetime.now(CN_TZ).strftime("%Y%m%d")


def _python_bin(repo_root: Path) -> str:
    python_bin = os.environ.get("PYTHON_BIN", str(repo_root / ".venv" / "bin" / "python"))
    if not Path(python_bin).exists():
        return sys.executable
    return python_bin


def _launcher_module() -> str:
    run_mode = os.environ.get("EVOLVE_RUN_MODE", "demo_light").strip().lower()
    if run_mode == "real_dryrun":
        return "apps.launcher_real_dryrun"
    if run_mode == "live_light" or os.environ.get("EVOLVE_LIVE_LIGHT") == "1":
        return "apps.launcher_live_light"
    return "apps.launcher_demo"


def _log(message: str, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(CN_TZ).isoformat()}] {message}"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line)


def _run_once(
    repo_root: Path,
    output_dir: Path,
    env: Dict[str, str],
    run_tag: str,
    interval: str,
    max_loops: str,
) -> Tuple[Path, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    python_bin = _python_bin(repo_root)
    cmd = [
        python_bin,
        "-u",
        "-m",
        _launcher_module(),
        "trade",
        "--interval",
        interval,
        "--log-level",
        "INFO",
        "--max-loops",
        max_loops,
    ]
    stdout_path = output_dir / f"{run_tag}_stdout.log"
    stderr_path = output_dir / f"{run_tag}_stderr.log"
    exit_code = run_subprocess(cmd, env, stdout_path, stderr_path)
    summary_path = summarize_run(run_tag=run_tag, run_dir=output_dir, repo_root=repo_root, output_dir=output_dir)
    return summary_path, exit_code


def _candidate_grid(base_env: Dict[str, str], max_candidates: int) -> List[Dict[str, str]]:
    rate_values = ["0.3", "0.5", "0.7"]
    conc_values = ["1", "2"]
    alpha_values = ["balanced", "aggressive"]
    candidates: List[Dict[str, str]] = []
    for rate in rate_values:
        for conc in conc_values:
            for alpha in alpha_values:
                patch = {
                    "SERVICE_REST_RATE_LIMIT_PER_SEC": rate,
                    "SERVICE_REST_MAX_CONCURRENCY": conc,
                    "DEMO_ALPHA_MODE": alpha,
                }
                if (
                    base_env.get("SERVICE_REST_RATE_LIMIT_PER_SEC") == rate
                    and base_env.get("SERVICE_REST_MAX_CONCURRENCY") == conc
                    and base_env.get("DEMO_ALPHA_MODE") == alpha
                ):
                    continue
                candidates.append(patch)
                if len(candidates) >= max_candidates:
                    return candidates
    return candidates


def _latest_guardian_health(repo_root: Path) -> Tuple[str, Dict]:
    guardian_root = repo_root / "out" / "guardian"
    if not guardian_root.exists():
        return ("", {})
    latest = None
    for path in guardian_root.rglob("health.json"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if latest is None or stat.st_mtime > latest[0]:
            latest = (stat.st_mtime, path)
    if not latest:
        return ("", {})
    try:
        data = json.loads(latest[1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    return (str(latest[1]), data)


def _latest_compare(repo_root: Path) -> Tuple[str, Dict]:
    root = repo_root / "out" / "evolution"
    latest = None
    for path in root.rglob("compare.json"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if latest is None or stat.st_mtime > latest[0]:
            latest = (stat.st_mtime, path)
    if not latest:
        return ("", {})
    try:
        data = json.loads(latest[1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    return (str(latest[1]), data)


def _latest_decision_patch(repo_root: Path) -> Tuple[str, Dict[str, str]]:
    review_root = repo_root / "out" / "review"
    if not review_root.exists():
        return ("", {})
    latest = None
    for path in review_root.rglob("DECISION.env"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if latest is None or stat.st_mtime > latest[0]:
            latest = (stat.st_mtime, path)
    if not latest:
        return ("", {})
    return (str(latest[1]), load_env_file(latest[1]))


def _load_state(repo_root: Path) -> Dict:
    state_path = repo_root / "out" / "evolution" / "state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _build_proposal(output_dir: Path, baseline_summary: Dict, env_patch: Dict[str, str], rationale: str) -> Path:
    proposal_path = output_dir / "proposal.json"
    proposal = {
        "proposal_id": output_dir.name,
        "baseline_run_id": baseline_summary.get("run_id"),
        "env_patch": env_patch,
        "rationale": rationale,
        "safety": {
            "POLY_DRY_RUN": baseline_summary.get("dry_run", True),
            "RUNNER_FETCH_MODE": baseline_summary.get("mode", "light"),
            "PAPER_TRADING": baseline_summary.get("paper_trading", True),
        },
    }
    write_json(proposal_path, proposal)
    return proposal_path


def run_daily(repo_root: Path, output_root: Path, max_candidates: int) -> Path:
    base_env = load_config_layers(repo_root)

    if os.environ.get("ENABLE_LIVE_TRADING") != "1":
        base_env["POLY_DRY_RUN"] = "true"
        base_env["PAPER_TRADING"] = "1"

    output_dir = ensure_dir(output_root)
    run_log = output_dir / "run.log"

    guardian_path, guardian_data = _latest_guardian_health(repo_root)
    guardian_unhealthy = guardian_data.get("healthy") is False

    state = _load_state(repo_root)
    frozen = bool(state.get("frozen"))
    failure_streak = int(state.get("failure_streak") or 0)
    freeze_limit = int(os.environ.get("EVOLVE_FREEZE_LIMIT", "3"))

    analysis_only = os.environ.get("EVOLVE_ANALYSIS_ONLY", "1") == "1"
    analysis_only = analysis_only or guardian_unhealthy or frozen or failure_streak >= freeze_limit

    decision_path, decision_patch = _latest_decision_patch(repo_root)

    _log(f"analysis_only={analysis_only} guardian_unhealthy={guardian_unhealthy} frozen={frozen}", run_log)
    if decision_patch:
        _log(f"decision_patch={decision_patch} (from {decision_path})", run_log)

    use_runtime = os.environ.get("EVOLVE_USE_LOBSTER_RUNTIME") == "1"
    if guardian_unhealthy:
        result = {
            "mode": "skipped",
            "analysis_only": True,
            "guardian_health": guardian_path,
            "reason": "guardian_unhealthy",
            "decision_path": decision_path,
        }
        write_json(output_dir / "result.json", result)
        review_md = output_dir / "review.md"
        lines = [
            "# Daily Evolution Review",
            "",
            f"- date: {datetime.now(CN_TZ).date().isoformat()}",
            "- status: skipped",
            "- reason: guardian_unhealthy",
            f"- analysis_only: {analysis_only}",
            "",
            "## Guardian Health (latest)",
        ]
        if guardian_path:
            lines.append(f"- health_path: {guardian_path}")
            lines.append(f"- healthy: {guardian_data.get('healthy')}")
            lines.append(f"- http_success_rate: {guardian_data.get('rates', {}).get('http_success_rate')}")
            lines.append(f"- error_rate: {guardian_data.get('rates', {}).get('error_rate')}")
            lines.append(f"- signal_rate: {guardian_data.get('rates', {}).get('signal_rate')}")
        else:
            lines.append("- health_path: (none)")
        lines.append("")
        lines.append("## Rollback")
        lines.append("- To rollback: run `scripts/rollback_to_last_good.sh`")
        review_md.write_text("\n".join(lines), encoding="utf-8")
        return review_md

    if use_runtime:
        cli = locate_cli()
        if cli.get("lobster_mode") == "missing":
            use_runtime = False

    if use_runtime:
        python_bin = _python_bin(repo_root)
        runtime_out = output_dir / "runtime"
        runtime_out.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        if analysis_only:
            env["EVOLVE_ANALYSIS_ONLY"] = "1"
        if decision_path:
            env["EVOLVE_DECISION_PATH"] = decision_path
        cmd = [
            python_bin,
            "tools/evolution/run_lobster_workflow.py",
            "--workflow",
            "workflows/pm_evolution_demo.lobster",
        ]
        run_subprocess(cmd, env, runtime_out / "runtime_stdout.log", runtime_out / "runtime_stderr.log")

        compare_path, compare_data = _latest_compare(repo_root)
        fitness = compare_data.get("fitness") or {}
        adopt = fitness.get("adopt") is True and not analysis_only

        if adopt:
            state_path = repo_root / "out" / "evolution" / "state.json"
            if state_path.exists():
                state_payload = json.loads(state_path.read_text(encoding="utf-8"))
                best_config = state_payload.get("best_config") or {}
                if best_config:
                    promote_candidate(best_config, repo_root)
            sync_from_state_json(repo_root)

        result = {
            "mode": "runtime",
            "analysis_only": analysis_only,
            "guardian_health": guardian_path,
            "compare_json": compare_path,
            "adopt": adopt,
            "decision_path": decision_path,
        }
        write_json(output_dir / "result.json", result)

        review_md = output_dir / "review.md"
        lines = [
            "# Daily Evolution Review",
            "",
            f"- date: {datetime.now(CN_TZ).date().isoformat()}",
            f"- compare_json: {compare_path}",
            f"- adopt: {adopt}",
            f"- analysis_only: {analysis_only}",
            "",
            "## Guardian Health (latest)",
        ]
        if guardian_path:
            lines.append(f"- health_path: {guardian_path}")
            lines.append(f"- healthy: {guardian_data.get('healthy')}")
            lines.append(f"- http_success_rate: {guardian_data.get('rates', {}).get('http_success_rate')}")
            lines.append(f"- error_rate: {guardian_data.get('rates', {}).get('error_rate')}")
            lines.append(f"- signal_rate: {guardian_data.get('rates', {}).get('signal_rate')}")
        else:
            lines.append("- health_path: (none)")
        lines.append("")
        lines.append("## Rollback")
        lines.append("- To rollback: run `scripts/rollback_to_last_good.sh`")
        review_md.write_text("\n".join(lines), encoding="utf-8")
        return review_md

    interval = os.environ.get("EVOLVE_DAILY_INTERVAL_SECS", "60")
    max_loops = os.environ.get("EVOLVE_DAILY_MAX_LOOPS", "1")

    baseline_dir = output_dir / "baseline"
    baseline_summary_path, baseline_rc = _run_once(
        repo_root, baseline_dir, base_env, "baseline", interval, max_loops
    )
    baseline_summary = json.loads(baseline_summary_path.read_text(encoding="utf-8"))
    if baseline_rc != 0:
        _log("baseline failed; using last_good.env", run_log)
        last_good_env = load_env_file(repo_root / "config" / "evolution" / "last_good.env")
        if last_good_env:
            baseline_summary_path, _ = _run_once(
                repo_root,
                output_dir / "baseline_last_good",
                {**base_env, **last_good_env},
                "baseline",
                interval,
                max_loops,
            )
            baseline_summary = json.loads(baseline_summary_path.read_text(encoding="utf-8"))

    candidates = _candidate_grid(base_env, max_candidates)
    candidate_results = []
    for idx, patch in enumerate(candidates, start=1):
        env = dict(base_env)
        env.update(patch)
        env.update(decision_patch)
        candidate_dir = output_dir / f"candidate_{idx}"
        summary_path, _ = _run_once(repo_root, candidate_dir, env, "candidate", interval, max_loops)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        score = compute_fitness(summary)
        candidate_results.append((patch, summary_path, score))

    if not candidate_results:
        raise RuntimeError("no candidates generated")

    candidate_results.sort(key=lambda item: item[2], reverse=True)
    best_patch, best_summary_path, best_score = candidate_results[0]
    merged_patch = dict(best_patch)
    merged_patch.update(decision_patch)

    rationale = "daily batch search; select highest fitness candidate"
    if guardian_unhealthy:
        rationale += "; guardian unstable => analysis-only"
    if decision_patch:
        rationale += "; includes manual DECISION.env override"

    proposal_path = _build_proposal(output_dir, baseline_summary, merged_patch, rationale)

    approval_rc = run_subprocess(
        [
            _python_bin(repo_root),
            "tools/evolution/approval_gate.py",
            "--proposal",
            str(proposal_path),
        ],
        os.environ.copy(),
        output_dir / "approval_stdout.log",
        output_dir / "approval_stderr.log",
    )
    if approval_rc != 0:
        analysis_only = True

    compare_env = os.environ.copy()
    if analysis_only:
        compare_env["EVOLVE_ANALYSIS_ONLY"] = "1"

    run_subprocess(
        [
            _python_bin(repo_root),
            "tools/evolution/compare.py",
            "--baseline-summary",
            str(baseline_summary_path),
            "--candidate-summary",
            str(best_summary_path),
            "--proposal",
            str(proposal_path),
            "--output-dir",
            str(output_dir),
        ],
        compare_env,
        output_dir / "compare_stdout.log",
        output_dir / "compare_stderr.log",
    )

    compare_json = output_dir / "compare.json"
    compare_data = json.loads(compare_json.read_text(encoding="utf-8"))
    adopt = (compare_data.get("fitness") or {}).get("adopt") is True and not analysis_only

    if adopt:
        promote_candidate({**base_env, **merged_patch}, repo_root)
    sync_from_state_json(repo_root)

    result = {
        "mode": "demo",
        "analysis_only": analysis_only,
        "guardian_health": guardian_path,
        "baseline_summary": str(baseline_summary_path),
        "candidate_summary": str(best_summary_path),
        "compare_json": str(compare_json),
        "adopt": adopt,
        "decision_path": decision_path,
        "approval_rc": approval_rc,
    }
    write_json(output_dir / "result.json", result)

    review_md = output_dir / "review.md"
    lines = [
        "# Daily Evolution Review",
        "",
        f"- date: {datetime.now(CN_TZ).date().isoformat()}",
        f"- baseline_summary: {baseline_summary_path}",
        f"- best_candidate_summary: {best_summary_path}",
        f"- compare_md: {output_dir / 'compare.md'}",
        f"- adopt: {adopt}",
        f"- analysis_only: {analysis_only}",
        "",
        "## Candidate Scores",
    ]
    for patch, summary_path, score in candidate_results:
        lines.append(f"- score={score:.6f} patch={patch} summary={summary_path}")
    lines.append("")
    lines.append("## Guardian Health (latest)")
    if guardian_path:
        lines.append(f"- health_path: {guardian_path}")
        lines.append(f"- healthy: {guardian_data.get('healthy')}")
        lines.append(f"- http_success_rate: {guardian_data.get('rates', {}).get('http_success_rate')}")
        lines.append(f"- error_rate: {guardian_data.get('rates', {}).get('error_rate')}")
        lines.append(f"- signal_rate: {guardian_data.get('rates', {}).get('signal_rate')}")
    else:
        lines.append("- health_path: (none)")
    lines.append("")
    lines.append("## Rollback")
    lines.append("- To rollback: run `scripts/rollback_to_last_good.sh`")

    review_md.write_text("\n".join(lines), encoding="utf-8")
    return review_md


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily evolution driver.")
    parser.add_argument("--output-root", default="out/evolution/daily", help="Output root")
    parser.add_argument("--max-candidates", default="3", help="Max candidates")
    args = parser.parse_args()

    repo_root = Path(".").resolve()
    ts_dir = _china_date()
    output_root = Path(args.output_root) / ts_dir
    review_md = run_daily(repo_root, output_root, int(args.max_candidates))
    print(str(review_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
