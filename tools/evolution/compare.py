from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import safe_load_json, write_json

METRICS = [
    "universe_size",
    "candidates_written_n",
    "evaluated_n",
    "signaled_n",
    "paper_open_attempted_n",
    "processed_n",
    "approved_n",
    "rejected_n",
    "holds_n",
    "ev_nonempty_n",
    "allowed_to_trade_n",
    "exec_evidence_http_200_n",
    "exec_evidence_http_error_n",
    "rest_avg_ms",
    "rest_p95_ms",
    "ws_age_seconds",
    "market_fetch_ok_n",
    "market_fetch_err_n",
    "book_fetch_ok_n",
    "book_fetch_err_n",
    "net_pnl",
    "closes_n",
]


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    return str(value)


def compute_fitness(summary: Dict[str, Any]) -> float:
    signal_rate = float(summary.get("signal_rate") or 0.0)
    http_success_rate = float(summary.get("http_success_rate") or 0.0)
    error_rate = float(summary.get("error_rate") or 0.0)
    rest_p95_ms = summary.get("rest_p95_ms")
    try:
        rest_p95_ms_value = float(rest_p95_ms)
    except (TypeError, ValueError):
        rest_p95_ms_value = 0.0

    rest_p95_ms_norm = rest_p95_ms_value / 1000.0

    score = (
        2.0 * signal_rate
        + 1.5 * http_success_rate
        - 1.0 * rest_p95_ms_norm
        - 1.5 * error_rate
    )
    return float(score)


def _stability_conclusion(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    base_http = baseline.get("exec_evidence_http_200_n") or 0
    cand_http = candidate.get("exec_evidence_http_200_n") or 0
    base_ev = baseline.get("ev_nonempty_n") or 0
    cand_ev = candidate.get("ev_nonempty_n") or 0

    if cand_http > base_http and cand_ev >= base_ev:
        return "candidate shows improved REST stability (higher http_200_n)"
    if cand_http == base_http and cand_ev > base_ev:
        return "candidate shows richer EV coverage"
    if cand_http == base_http and cand_ev == base_ev:
        return "no clear stability improvement detected"
    return "candidate did not improve stability metrics"


def _resolve_mode(summary: Dict[str, Any]) -> str:
    return (
        summary.get("run_mode")
        or summary.get("pipeline_mode")
        or summary.get("mode")
        or "unknown"
    )


def _safety_line(mode_value: str) -> str:
    lowered = str(mode_value).lower()
    if "real_dryrun" in lowered:
        return "real_dryrun uses Polymarket REST/WS data only; dry-run and paper trading only; no real orders were submitted."
    if "live_light" in lowered or "live" in lowered:
        return "live_light uses py_clob_client read-only; dry-run and paper trading only; no real orders were submitted."
    return "demo mode uses launcher_demo; dry-run and paper trading only; no real orders were submitted."


def _demo_verdict_lines(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> list[str]:
    base_http = baseline.get("exec_evidence_http_200_n") or 0
    cand_http = candidate.get("exec_evidence_http_200_n") or 0
    base_signaled = baseline.get("signaled_n") or 0
    cand_signaled = candidate.get("signaled_n") or 0
    base_processed = baseline.get("processed_n") or 0
    cand_processed = candidate.get("processed_n") or 0
    base_mode = baseline.get("demo_alpha_mode")
    cand_mode = candidate.get("demo_alpha_mode")
    base_edge = baseline.get("demo_edge_bps")
    cand_edge = candidate.get("demo_edge_bps")
    base_spread = baseline.get("demo_max_spread_bps")
    cand_spread = candidate.get("demo_max_spread_bps")
    base_p95 = baseline.get("rest_p95_ms")
    cand_p95 = candidate.get("rest_p95_ms")

    rest_status = "improved" if cand_http > base_http else "no change/decline"
    signal_status = (
        "improved"
        if (cand_signaled > base_signaled or cand_processed > base_processed)
        else "no change/decline"
    )

    param_line = (
        f"- Params: alpha_mode {_format_value(base_mode)} → {_format_value(cand_mode)}, "
        f"edge_bps {_format_value(base_edge)} → {_format_value(cand_edge)}, "
        f"max_spread_bps {_format_value(base_spread)} → {_format_value(cand_spread)} "
        f"⇒ signals {base_signaled} → {cand_signaled}, processed {base_processed} → {cand_processed}"
    )

    lines = [
        f"- REST stability: {rest_status} (http_200_n {base_http} → {cand_http})",
        f"- Signal/processing: {signal_status} (signaled {base_signaled} → {cand_signaled}, processed {base_processed} → {cand_processed})",
        param_line,
    ]
    if base_p95 is not None or cand_p95 is not None:
        lines.append(
            f"- REST latency p95: {_format_value(base_p95)} → {_format_value(cand_p95)} ms"
        )
    return lines


def build_compare(
    baseline_summary_path: Path,
    candidate_summary_path: Path,
    proposal_path: Path,
    output_dir: Optional[Path] = None,
) -> Path:
    baseline = safe_load_json(baseline_summary_path)
    candidate = safe_load_json(candidate_summary_path)
    proposal = safe_load_json(proposal_path)

    if baseline is None or candidate is None or proposal is None:
        raise ValueError("compare inputs missing")

    proposal_id = proposal.get("proposal_id")
    if output_dir is None:
        output_dir = proposal_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_score = compute_fitness(baseline)
    candidate_score = compute_fitness(candidate)
    threshold = float(os.environ.get("EVOLVE_FITNESS_THRESHOLD", "0.05") or 0.05)
    adopt = candidate_score > (baseline_score + threshold)

    state_path = Path("out") / "evolution" / "state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    best_score = state.get("best_score")
    failure_streak = int(state.get("failure_streak") or 0)

    freeze_limit = int(os.environ.get("EVOLVE_FREEZE_LIMIT", "3") or 3)
    frozen = failure_streak >= freeze_limit
    if os.environ.get("EVOLVE_UNFREEZE") == "1":
        frozen = False
        failure_streak = 0
    if frozen:
        adopt = False
    if os.environ.get("EVOLVE_ANALYSIS_ONLY") == "1":
        adopt = False

    if adopt:
        best_score = candidate_score
        state["best_config"] = proposal.get("env_patch", {})
        failure_streak = 0
    else:
        failure_streak += 1 if not frozen else 0

    state["best_score"] = best_score if best_score is not None else candidate_score
    state["last_run_id"] = candidate.get("run_id")
    state["failure_streak"] = failure_streak
    state["frozen"] = frozen

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    if frozen:
        notice_path = state_path.parent / "freeze_notice.md"
        notice_lines = [
            "# Evolution Frozen",
            "",
            f"- failure_streak: {failure_streak}",
            "- reason: failure_streak >= 3",
            "- action: set EVOLVE_UNFREEZE=1 or reset state.json to unfreeze",
        ]
        notice_path.write_text("\n".join(notice_lines), encoding="utf-8")

    compare = {
        "proposal_id": proposal_id,
        "baseline": baseline,
        "candidate": candidate,
        "env_patch": proposal.get("env_patch", {}),
        "conclusion": _stability_conclusion(baseline, candidate),
        "fitness": {
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "delta_score": candidate_score - baseline_score,
            "threshold": threshold,
            "adopt": adopt,
            "frozen": frozen,
            "analysis_only": os.environ.get("EVOLVE_ANALYSIS_ONLY") == "1",
            "freeze_limit": freeze_limit,
        },
        "state_path": str(state_path),
    }

    compare_json_path = output_dir / "compare.json"
    write_json(compare_json_path, compare)

    lines = []
    lines.append("# Evolution Compare")
    lines.append("")
    lines.append(f"Baseline run_id: {baseline.get('run_id')}")
    lines.append(f"Candidate run_id: {candidate.get('run_id')}")
    lines.append("")
    lines.append("## Mode")
    base_mode = _resolve_mode(baseline)
    cand_mode = _resolve_mode(candidate)
    lines.append(f"- baseline: {base_mode}")
    lines.append(f"- candidate: {cand_mode}")
    lines.append("")
    lines.append("## Env Diff")
    env_patch = proposal.get("env_patch", {})
    if not env_patch:
        lines.append("(none)")
    else:
        for key, value in env_patch.items():
            lines.append(f"- {key}={value}")
    lines.append("")
    lines.append("## Core Metrics")
    lines.append("| metric | baseline | candidate |")
    lines.append("| --- | --- | --- |")
    for metric in METRICS:
        lines.append(
            f"| {metric} | {_format_value(baseline.get(metric))} | {_format_value(candidate.get(metric))} |"
        )
    lines.append("")
    lines.append("## Fitness")
    lines.append(f"- baseline_score: {baseline_score:.6f}")
    lines.append(f"- candidate_score: {candidate_score:.6f}")
    lines.append(f"- delta_score: {(candidate_score - baseline_score):.6f}")
    lines.append(f"- threshold: {threshold}")
    lines.append(f"- adopt: {adopt}")
    if frozen:
        lines.append("- frozen: true (failure_streak >= 3)")
    if os.environ.get("EVOLVE_ANALYSIS_ONLY") == "1":
        lines.append("- analysis_only: true (no adopt)")
    lines.append("")
    lines.append("## Risk Notes")
    risk_lines = []
    env_patch = proposal.get("env_patch", {})
    try:
        conc = float(env_patch.get("SERVICE_REST_MAX_CONCURRENCY", "1"))
    except (TypeError, ValueError):
        conc = 1.0
    try:
        rate = float(env_patch.get("SERVICE_REST_RATE_LIMIT_PER_SEC", "0.3"))
    except (TypeError, ValueError):
        rate = 0.3
    if conc > 2:
        risk_lines.append(f"- REST concurrency high: {conc}")
    if rate > 1.0:
        risk_lines.append(f"- REST rate high: {rate}")
    if str(env_patch.get("SERVICE_USE_WS", "false")).lower() == "true":
        risk_lines.append("- WS enabled; ensure proxies/stability validated")
    if str(env_patch.get("DEMO_ALPHA_MODE", "")).lower() == "aggressive":
        risk_lines.append("- Aggressive alpha mode (demo) may increase churn")
    if not risk_lines:
        risk_lines.append("- No elevated risk flags; patch within safe demo bounds")
    lines.extend(risk_lines)
    lines.append("")
    lines.append("## Demo Verdict")
    lines.extend(_demo_verdict_lines(baseline, candidate))
    lines.append("")
    lines.append("## Safety")
    lines.append(_safety_line(cand_mode))
    lines.append("")
    lines.append("## Conclusion")
    lines.append(_stability_conclusion(baseline, candidate))

    compare_md_path = output_dir / "compare.md"
    compare_md_path.write_text("\n".join(lines), encoding="utf-8")

    return compare_md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare baseline and candidate runs.")
    parser.add_argument("--baseline-summary", required=True, help="Baseline summary.json")
    parser.add_argument("--candidate-summary", required=True, help="Candidate summary.json")
    parser.add_argument("--proposal", required=True, help="proposal.json")
    parser.add_argument("--output-dir", default="", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    compare_md = build_compare(
        Path(args.baseline_summary),
        Path(args.candidate_summary),
        Path(args.proposal),
        output_dir=output_dir,
    )
    print(str(compare_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
