from __future__ import annotations

from pathlib import Path

from tools.evolution.common import write_json
from tools.evolution.compare import build_compare
from tools.evolution.propose import generate_proposal


def test_propose_and_compare(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    baseline_dir = tmp_path / "out" / "evolution" / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)

    baseline_summary = {
        "run_tag": "baseline",
        "run_id": "20260211_120000_001",
        "mode": "light",
        "dry_run": True,
        "paper_trading": True,
        "universe_size": 10,
        "candidates_written_n": 5,
        "exec_evidence_http_200_n": 3,
        "ev_nonempty_n": 2,
        "fair_yes_nonempty_n": 2,
        "allowed_to_trade_n": 0,
        "net_pnl": 0.0,
        "opens_n": 0,
        "closes_n": 0,
        "missing_reasons": {},
    }

    baseline_summary_path = baseline_dir / "summary.json"
    write_json(baseline_summary_path, baseline_summary)

    proposal_path = generate_proposal(
        baseline_summary_path,
        tmp_path / "out" / "evolution",
    )
    proposal_dir = proposal_path.parent

    candidate_summary = {
        "run_tag": "candidate",
        "run_id": "20260211_121000_001",
        "mode": "light",
        "dry_run": True,
        "paper_trading": True,
        "universe_size": 12,
        "candidates_written_n": 6,
        "exec_evidence_http_200_n": 4,
        "ev_nonempty_n": 3,
        "fair_yes_nonempty_n": 3,
        "allowed_to_trade_n": 0,
        "net_pnl": 0.0,
        "opens_n": 0,
        "closes_n": 0,
        "missing_reasons": {},
    }

    candidate_summary_path = proposal_dir / "summary.json"
    write_json(candidate_summary_path, candidate_summary)

    compare_md = build_compare(
        baseline_summary_path,
        candidate_summary_path,
        proposal_path,
        output_dir=proposal_dir,
    )

    assert compare_md.exists()
    assert (proposal_dir / "compare.json").exists()
