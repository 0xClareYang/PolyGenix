from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import read_text, safe_load_json, write_json
from tools.evolution.config_store import load_env_file

ISSUE_PATTERNS = [
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"429", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"rate limit", re.IGNORECASE),
    re.compile(r"connection reset", re.IGNORECASE),
    re.compile(r"connection aborted", re.IGNORECASE),
    re.compile(r"max retries", re.IGNORECASE),
    re.compile(r"server error", re.IGNORECASE),
]


def _detect_issues(texts: list[str]) -> list[str]:
    issues: list[str] = []
    for text in texts:
        for pattern in ISSUE_PATTERNS:
            if pattern.search(text):
                issues.append(pattern.pattern)
    return sorted(set(issues))


def _load_log_texts(baseline_dir: Path, repo_root: Path) -> list[str]:
    texts: list[str] = []
    for path in baseline_dir.glob("*_stdout.log"):
        texts.append(read_text(path))
    for path in baseline_dir.glob("*_stderr.log"):
        texts.append(read_text(path))
    main_log = repo_root / "logs" / "polymarket.log"
    if main_log.exists():
        texts.append(read_text(main_log))
    return texts


def generate_proposal(baseline_summary_path: Path, output_root: Path) -> Path:
    baseline_summary = safe_load_json(baseline_summary_path)
    if baseline_summary is None:
        raise ValueError(f"Missing baseline summary: {baseline_summary_path}")

    baseline_run_id = baseline_summary.get("run_id")
    baseline_dir = baseline_summary_path.parent
    repo_root = Path(".").resolve()
    issues = _detect_issues(_load_log_texts(baseline_dir, repo_root))

    proposal_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}"
    output_dir = output_root / proposal_id

    env_patch = {
        "SERVICE_REST_RATE_LIMIT_PER_SEC": "0.5",
        "SERVICE_REST_MAX_CONCURRENCY": "2",
        "DEMO_ALPHA_MODE": "aggressive",
        "DEMO_EDGE_BPS": "60",
        "DEMO_MAX_SPREAD_BPS": "500",
    }

    decision_patch = {}
    decision_path = os.environ.get("EVOLVE_DECISION_PATH")
    if decision_path:
        decision_patch = load_env_file(Path(decision_path))
    else:
        review_root = Path("out") / "review"
        latest = None
        for path in review_root.rglob("DECISION.env"):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if latest is None or stat.st_mtime > latest[0]:
                latest = (stat.st_mtime, path)
        if latest:
            decision_path = str(latest[1])
            decision_patch = load_env_file(latest[1])

    if decision_patch:
        env_patch.update({str(k): str(v) for k, v in decision_patch.items()})

    baseline_http_ok = baseline_summary.get("exec_evidence_http_200_n")
    baseline_http_err = baseline_summary.get("exec_evidence_http_error_n")
    baseline_signaled = baseline_summary.get("signaled_n")
    baseline_processed = baseline_summary.get("processed_n")
    baseline_rest_p95 = baseline_summary.get("rest_p95_ms")

    rationale_lines = [
        "goal: improve REST stability and signal throughput",
    ]
    if baseline_http_ok is not None or baseline_http_err is not None:
        rationale_lines.append(
            f"baseline http_200_n={baseline_http_ok} http_error_n={baseline_http_err}"
        )
    if baseline_signaled is not None or baseline_processed is not None:
        rationale_lines.append(
            f"baseline signaled_n={baseline_signaled} processed_n={baseline_processed}"
        )
    if baseline_rest_p95 is not None:
        rationale_lines.append(f"baseline rest_p95_ms={baseline_rest_p95}")
    if issues:
        rationale_lines.append("detected issues: " + ", ".join(issues))
    rationale_lines.append(
        "proposal: raise REST pacing + adjust demo alpha/risk params"
    )
    if decision_patch:
        rationale_lines.append(f"manual decision override applied: {decision_path}")

    proposal: Dict[str, Any] = {
        "proposal_id": proposal_id,
        "baseline_run_id": baseline_run_id,
        "env_patch": env_patch,
        "rationale": "\n".join(rationale_lines[:10]),
        "decision_patch": decision_patch or None,
        "decision_path": decision_path,
        "rollback_env_patch": {
            "SERVICE_REST_RATE_LIMIT_PER_SEC": "0.3",
            "SERVICE_REST_MAX_CONCURRENCY": "1",
            "DEMO_ALPHA_MODE": "balanced",
            "DEMO_EDGE_BPS": "80",
            "DEMO_MAX_SPREAD_BPS": "400",
        },
        "safety": {
            "POLY_DRY_RUN": "true",
            "RUNNER_FETCH_MODE": "light",
            "PAPER_TRADING": "1",
        },
    }

    optional_env_patch = {
        "SERVICE_USE_WS": {
            "value": "true",
            "enabled": False,
            "reason": "WS not verified in baseline; keep off by default",
        }
    }
    proposal["optional_env_patch"] = optional_env_patch

    output_dir.mkdir(parents=True, exist_ok=True)
    proposal_path = output_dir / "proposal.json"
    write_json(proposal_path, proposal)
    return proposal_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a proposal from baseline summary.")
    parser.add_argument("--baseline-summary", required=True, help="Path to baseline summary.json")
    parser.add_argument("--output-root", default="out/evolution", help="Output root")
    args = parser.parse_args()

    proposal_path = generate_proposal(
        Path(args.baseline_summary),
        Path(args.output_root),
    )
    print(str(proposal_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
