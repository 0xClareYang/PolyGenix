from __future__ import annotations

from pathlib import Path

from tools.evolution.acceptance_parse import parse_from_file


def test_parse_direct_line(tmp_path: Path) -> None:
    log = tmp_path / "demo.out"
    log.write_text(
        "foo\ncompare_md_path=out/evolution/x/compare.md baseline_run_id=20260211_120000_001 candidate_run_id=20260211_120500_002\n",
        encoding="utf-8",
    )

    data = parse_from_file(log)
    assert data["compare_md_path"] == "out/evolution/x/compare.md"
    assert data["baseline_run_id"] == "20260211_120000_001"
    assert data["candidate_run_id"] == "20260211_120500_002"


def test_parse_result_line_path(tmp_path: Path) -> None:
    result_line = tmp_path / "result_line.txt"
    result_line.write_text(
        "compare_md_path=out/evolution/y/compare.md baseline_run_id=20260211_130000_003 candidate_run_id=20260211_130500_004\n",
        encoding="utf-8",
    )
    log = tmp_path / "runtime.out"
    log.write_text(f"result_line_path={result_line}\n", encoding="utf-8")

    data = parse_from_file(log)
    assert data["compare_md_path"] == "out/evolution/y/compare.md"
    assert data["baseline_run_id"] == "20260211_130000_003"
    assert data["candidate_run_id"] == "20260211_130500_004"
