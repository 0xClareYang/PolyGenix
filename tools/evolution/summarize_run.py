from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import ensure_dir, read_text, safe_load_json, write_json
from tools.evolution.parse_run_id import extract_run_id

RE_HTTP_200 = re.compile(r"http_200_n=(\d+)")
RE_HTTP_ERROR = re.compile(r"http_error_n=(\d+)")
RE_EV_NONEMPTY = re.compile(r"ev_nonempty_n=(\d+)")
RE_FAIR_NONEMPTY = re.compile(r"fair_yes_nonempty_n=(\d+)")
RE_ALLOWED_N = re.compile(r"allowed_to_trade_n=(\d+)")
RE_MARKETS_LEN = re.compile(r"markets_len=(\d+)")
RE_UNIVERSE = re.compile(r"universe_size=(\d+)")
RE_STRATEGY_UNIVERSE = re.compile(r"universe=(\d+)")
RE_STRATEGY_EVALUATED = re.compile(r"evaluated=(\d+)")
RE_STRATEGY_SIGNALED = re.compile(r"signaled=(\d+)")
RE_STRATEGY_PAPER = re.compile(r"paper_open_attempted=(\d+)")
RE_LOOP_PROCESSED = re.compile(r"processed=(\d+)")
RE_LOOP_APPROVED = re.compile(r"approved=(\d+)")
RE_LOOP_REJECTED = re.compile(r"rejected=(\d+)")
RE_LOOP_HOLDS = re.compile(r"holds=(\d+)")
RE_DRY_RUN = re.compile(r"POLY_DRY_RUN=(true|false)", re.IGNORECASE)
RE_PAPER = re.compile(r"PAPER_TRADING=(true|false)", re.IGNORECASE)
RE_RUNNER_MODE = re.compile(r"RUNNER_FETCH_MODE=([a-zA-Z0-9_]+)")
RE_DEMO_ALPHA = re.compile(r"\\[demo_alpha\\].*mode=([^ ]+)\\s+edge_bps=(\\d+)")
RE_DEMO_RISK = re.compile(r"\\[demo_risk\\].*max_spread_bps=(\\d+)")


def _bool_from_str(value: str) -> Optional[bool]:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _collect_log_files(run_dir: Path, repo_root: Path) -> list[Path]:
    files: list[Path] = []
    if run_dir.exists():
        files.extend(run_dir.glob("*_stdout.log"))
        files.extend(run_dir.glob("*_stderr.log"))
    main_log = repo_root / "logs" / "polymarket.log"
    if main_log.exists():
        files.append(main_log)
    files = [p for p in files if p.exists()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _scan_logs(files: Iterable[Path]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    for path in files:
        text = read_text(path)
        for line in text.splitlines():
            if "exec_evidence_http" in line:
                match = RE_HTTP_200.search(line)
                if match:
                    metrics["exec_evidence_http_200_n"] = int(match.group(1))
                match = RE_HTTP_ERROR.search(line)
                if match:
                    metrics["exec_evidence_http_error_n"] = int(match.group(1))
            if "[strategy_funnel]" in line:
                match = RE_STRATEGY_UNIVERSE.search(line)
                if match:
                    metrics["universe_size"] = int(match.group(1))
                match = RE_STRATEGY_EVALUATED.search(line)
                if match:
                    metrics["evaluated_n"] = int(match.group(1))
                match = RE_STRATEGY_SIGNALED.search(line)
                if match:
                    metrics["signaled_n"] = int(match.group(1))
                match = RE_STRATEGY_PAPER.search(line)
                if match:
                    metrics["paper_open_attempted_n"] = int(match.group(1))
            if "[loop_summary]" in line:
                match = RE_LOOP_PROCESSED.search(line)
                if match:
                    metrics["processed_n"] = int(match.group(1))
                match = RE_LOOP_APPROVED.search(line)
                if match:
                    metrics["approved_n"] = int(match.group(1))
                match = RE_LOOP_REJECTED.search(line)
                if match:
                    metrics["rejected_n"] = int(match.group(1))
                match = RE_LOOP_HOLDS.search(line)
                if match:
                    metrics["holds_n"] = int(match.group(1))
            if "ev_compute_stats" in line:
                match = RE_EV_NONEMPTY.search(line)
                if match:
                    metrics["ev_nonempty_n"] = int(match.group(1))
                match = RE_FAIR_NONEMPTY.search(line)
                if match:
                    metrics["fair_yes_nonempty_n"] = int(match.group(1))
            if "allowed_to_trade_n=" in line:
                match = RE_ALLOWED_N.search(line)
                if match:
                    metrics["allowed_to_trade_n"] = int(match.group(1))
            if "strategy_funnel" in line or "sampling" in line:
                match = RE_MARKETS_LEN.search(line)
                if match:
                    metrics["universe_size"] = int(match.group(1))
                match = RE_UNIVERSE.search(line)
                if match:
                    metrics["universe_size"] = int(match.group(1))
            if "RUNNER_FETCH_MODE" in line:
                match = RE_RUNNER_MODE.search(line)
                if match:
                    metrics["mode"] = match.group(1)
            if "[demo_alpha]" in line:
                match = RE_DEMO_ALPHA.search(line)
                if match:
                    metrics["demo_alpha_mode"] = match.group(1)
                    metrics["demo_edge_bps"] = int(match.group(2))
            if "[demo_risk]" in line:
                match = RE_DEMO_RISK.search(line)
                if match:
                    metrics["demo_max_spread_bps"] = int(match.group(1))
            if "POLY_DRY_RUN" in line:
                match = RE_DRY_RUN.search(line)
                if match:
                    metrics["dry_run"] = _bool_from_str(match.group(1))
            if "PAPER_TRADING" in line:
                match = RE_PAPER.search(line)
                if match:
                    metrics["paper_trading"] = _bool_from_str(match.group(1))
    return metrics


def _find_latest(paths: Iterable[Path]) -> Optional[Path]:
    files = [p for p in paths if p.exists() and p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _find_candidates_csv(repo_root: Path) -> Optional[Path]:
    patterns = [
        repo_root / "reports" / "phaseB" / "typea_candidates_*.csv",
        repo_root / "reports" / "phaseB" / "typeA_candidates_*.csv",
    ]
    for pattern in patterns:
        files = list(pattern.parent.glob(pattern.name))
        latest = _find_latest(files)
        if latest:
            return latest
    return None


def _count_candidates(path: Path) -> Tuple[int, Optional[int]]:
    count = 0
    allowed_count: Optional[int] = None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        allowed_keys = [
            key for key in (reader.fieldnames or []) if "allowed_to_trade" in key
        ]
        for row in reader:
            count += 1
            if allowed_keys:
                value = row.get(allowed_keys[0], "")
                parsed = _bool_from_str(str(value))
                if parsed is True:
                    allowed_count = (allowed_count or 0) + 1
                elif parsed is False:
                    allowed_count = allowed_count or 0
    return count, allowed_count


def _find_nested_numeric(obj: Any, keys: Iterable[str]) -> Optional[int]:
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        for value in obj.values():
            found = _find_nested_numeric(value, keys)
            if found is not None:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = _find_nested_numeric(value, keys)
            if found is not None:
                return found
    return None


def _find_nested_number(obj: Any, keys: Iterable[str]) -> Optional[float]:
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for value in obj.values():
            found = _find_nested_number(value, keys)
            if found is not None:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = _find_nested_number(value, keys)
            if found is not None:
                return found
    return None


def _read_pipeline_metrics(repo_root: Path) -> Dict[str, Any]:
    pipeline = safe_load_json(repo_root / "reports" / "pipeline_status.json")
    if not pipeline:
        return {}
    strategy = pipeline.get("strategy_funnel") if isinstance(pipeline, dict) else {}
    loop = pipeline.get("loop_summary") if isinstance(pipeline, dict) else {}
    exec_http = pipeline.get("exec_evidence_http") if isinstance(pipeline, dict) else {}
    demo_params = pipeline.get("demo_params") if isinstance(pipeline, dict) else {}

    return {
        "pipeline_mode": pipeline.get("mode") if isinstance(pipeline, dict) else None,
        "pipeline_source": pipeline.get("source") if isinstance(pipeline, dict) else None,
        "universe_size": _find_nested_numeric(
            strategy, ["universe", "universe_size", "markets_len", "markets_n", "markets_total"]
        ),
        "evaluated_n": _find_nested_numeric(strategy, ["evaluated", "eval", "eval_n"]),
        "signaled_n": _find_nested_numeric(strategy, ["signaled", "signal_n"]),
        "paper_open_attempted_n": _find_nested_numeric(strategy, ["paper_open_attempted"]),
        "processed_n": _find_nested_numeric(loop, ["processed"]),
        "approved_n": _find_nested_numeric(loop, ["approved"]),
        "rejected_n": _find_nested_numeric(loop, ["rejected"]),
        "holds_n": _find_nested_numeric(loop, ["holds", "hold"]),
        "exec_evidence_http_200_n": _find_nested_numeric(exec_http, ["http_200_n"]),
        "exec_evidence_http_error_n": _find_nested_numeric(exec_http, ["http_error_n"]),
        "rest_avg_ms": _find_nested_number(
            pipeline,
            ["rest_avg_ms", "rest_avg", "rest_mean_ms", "rest_mean", "rest_latency_avg_ms"],
        ),
        "rest_p95_ms": _find_nested_number(
            pipeline,
            ["rest_p95_ms", "rest_p95", "rest_latency_p95_ms", "rest_latency_p95"],
        ),
        "ws_age_seconds": _find_nested_number(pipeline, ["ws_age_seconds", "ws_age_s", "ws_age"]),
        "ws_status": pipeline.get("ws_status") if isinstance(pipeline, dict) else None,
        "market_fetch_ok_n": _find_nested_numeric(pipeline, ["market_fetch_ok_n", "market_fetch_ok"]),
        "market_fetch_err_n": _find_nested_numeric(pipeline, ["market_fetch_err_n", "market_fetch_err"]),
        "book_fetch_ok_n": _find_nested_numeric(pipeline, ["book_fetch_ok_n", "book_fetch_ok"]),
        "book_fetch_err_n": _find_nested_numeric(pipeline, ["book_fetch_err_n", "book_fetch_err"]),
        "demo_alpha_mode": demo_params.get("alpha_mode") if isinstance(demo_params, dict) else None,
        "demo_edge_bps": demo_params.get("edge_bps") if isinstance(demo_params, dict) else None,
        "demo_max_spread_bps": demo_params.get("max_spread_bps") if isinstance(demo_params, dict) else None,
    }


def _load_pnl_summary(repo_root: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    candidates = list((repo_root / "reports").glob("**/paper_pnl_summary.json"))
    latest = _find_latest(candidates)
    if not latest:
        return None, None
    return safe_load_json(latest), latest


def _summarize_trade_journal(repo_root: Path) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    journal = repo_root / "logs" / "trade_journal.jsonl"
    if not journal.exists():
        return None, None, None
    opens = 0
    closes = 0
    total = 0
    for line in read_text(journal).splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("event", "action", "type"):
            value = payload.get(key)
            if not isinstance(value, str):
                continue
            lowered = value.lower()
            if "open" in lowered:
                opens += 1
            if "close" in lowered:
                closes += 1
    return total, opens, closes


def summarize_run(
    run_tag: str,
    run_dir: Path,
    repo_root: Path,
    run_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    missing_reasons: Dict[str, str] = {}
    log_files = _collect_log_files(run_dir, repo_root)
    log_metrics = _scan_logs(log_files)

    run_id_value = run_id
    run_id_source = None
    run_id_confidence = None
    if run_id_value is None:
        run_id_value, run_id_source, run_id_confidence = extract_run_id(log_files)
    if run_id_value is None:
        missing_reasons["run_id"] = "not found in logs"

    mode = os.environ.get("RUNNER_FETCH_MODE") or log_metrics.get("mode")
    if mode is None:
        missing_reasons["mode"] = "not found in env or logs"

    dry_run = None
    if "POLY_DRY_RUN" in os.environ:
        dry_run = _bool_from_str(os.environ.get("POLY_DRY_RUN", ""))
    if dry_run is None:
        dry_run = log_metrics.get("dry_run")
    if dry_run is None:
        missing_reasons["dry_run"] = "not found in env or logs"

    paper_trading = None
    if "PAPER_TRADING" in os.environ:
        paper_trading = _bool_from_str(os.environ.get("PAPER_TRADING", ""))
    if paper_trading is None:
        paper_trading = log_metrics.get("paper_trading")
    if paper_trading is None:
        missing_reasons["paper_trading"] = "not found in env or logs"

    pipeline_metrics = _read_pipeline_metrics(repo_root)

    run_mode = pipeline_metrics.get("pipeline_mode") or pipeline_metrics.get("pipeline_source")
    if isinstance(run_mode, str):
        if "launcher_real_dryrun" in run_mode:
            run_mode = "real_dryrun"
        if "launcher_demo" in run_mode:
            run_mode = "demo_light"
    if run_mode is None and os.environ.get("EVOLVE_RUN_MODE"):
        run_mode = os.environ.get("EVOLVE_RUN_MODE")
    if run_mode is None and os.environ.get("EVOLVE_LIVE_LIGHT") == "1":
        run_mode = "live_light"
    if run_mode is None:
        missing_reasons["run_mode"] = "not found in pipeline_status.json"

    universe_size = pipeline_metrics.get("universe_size") or log_metrics.get("universe_size")
    if universe_size is None:
        missing_reasons["universe_size"] = "not found in pipeline_status.json or logs"

    candidates_written_n = None
    allowed_to_trade_n = log_metrics.get("allowed_to_trade_n")
    candidates_csv = _find_candidates_csv(repo_root)
    if candidates_csv:
        candidates_written_n, allowed_from_csv = _count_candidates(candidates_csv)
        if allowed_to_trade_n is None:
            allowed_to_trade_n = allowed_from_csv
    else:
        missing_reasons["candidates_written_n"] = "candidates csv missing"

    exec_evidence_http_200_n = (
        log_metrics.get("exec_evidence_http_200_n")
        or pipeline_metrics.get("exec_evidence_http_200_n")
    )
    if exec_evidence_http_200_n is None:
        missing_reasons["exec_evidence_http_200_n"] = "not found in logs"

    exec_evidence_http_error_n = (
        log_metrics.get("exec_evidence_http_error_n")
        or pipeline_metrics.get("exec_evidence_http_error_n")
    )
    if exec_evidence_http_error_n is None:
        missing_reasons["exec_evidence_http_error_n"] = "not found in logs"

    ev_nonempty_n = log_metrics.get("ev_nonempty_n")
    if ev_nonempty_n is None:
        missing_reasons["ev_nonempty_n"] = "not found in logs"

    fair_yes_nonempty_n = log_metrics.get("fair_yes_nonempty_n")
    if fair_yes_nonempty_n is None:
        missing_reasons["fair_yes_nonempty_n"] = "not found in logs"

    if allowed_to_trade_n is None:
        missing_reasons["allowed_to_trade_n"] = "not found in logs or candidates csv"

    evaluated_n = log_metrics.get("evaluated_n") or pipeline_metrics.get("evaluated_n")
    if evaluated_n is None:
        missing_reasons["evaluated_n"] = "not found in logs"

    signaled_n = log_metrics.get("signaled_n") or pipeline_metrics.get("signaled_n")
    if signaled_n is None:
        missing_reasons["signaled_n"] = "not found in logs"

    paper_open_attempted_n = (
        log_metrics.get("paper_open_attempted_n") or pipeline_metrics.get("paper_open_attempted_n")
    )
    if paper_open_attempted_n is None:
        missing_reasons["paper_open_attempted_n"] = "not found in logs"

    processed_n = log_metrics.get("processed_n") or pipeline_metrics.get("processed_n")
    if processed_n is None:
        missing_reasons["processed_n"] = "not found in logs"

    approved_n = log_metrics.get("approved_n") or pipeline_metrics.get("approved_n")
    if approved_n is None:
        missing_reasons["approved_n"] = "not found in logs"

    rejected_n = log_metrics.get("rejected_n") or pipeline_metrics.get("rejected_n")
    if rejected_n is None:
        missing_reasons["rejected_n"] = "not found in logs"

    holds_n = log_metrics.get("holds_n") or pipeline_metrics.get("holds_n")
    if holds_n is None:
        missing_reasons["holds_n"] = "not found in logs"

    demo_alpha_mode = log_metrics.get("demo_alpha_mode") or pipeline_metrics.get("demo_alpha_mode")
    if demo_alpha_mode is None:
        missing_reasons["demo_alpha_mode"] = "not found in logs"

    demo_edge_bps = log_metrics.get("demo_edge_bps") or pipeline_metrics.get("demo_edge_bps")
    if demo_edge_bps is None:
        missing_reasons["demo_edge_bps"] = "not found in logs"

    demo_max_spread_bps = (
        log_metrics.get("demo_max_spread_bps") or pipeline_metrics.get("demo_max_spread_bps")
    )
    if demo_max_spread_bps is None:
        missing_reasons["demo_max_spread_bps"] = "not found in logs"

    rest_avg_ms = pipeline_metrics.get("rest_avg_ms")
    rest_p95_ms = pipeline_metrics.get("rest_p95_ms")
    ws_age_seconds = pipeline_metrics.get("ws_age_seconds")
    ws_status = pipeline_metrics.get("ws_status")
    market_fetch_ok_n = pipeline_metrics.get("market_fetch_ok_n")
    market_fetch_err_n = pipeline_metrics.get("market_fetch_err_n")
    book_fetch_ok_n = pipeline_metrics.get("book_fetch_ok_n")
    book_fetch_err_n = pipeline_metrics.get("book_fetch_err_n")

    if rest_p95_ms is None and run_mode in {"live_light", "real_dryrun"}:
        missing_reasons["rest_p95_ms"] = "not found in pipeline_status.json"
    if book_fetch_ok_n is None and run_mode in {"live_light", "real_dryrun"}:
        missing_reasons["book_fetch_ok_n"] = "not found in pipeline_status.json"

    net_pnl = None
    opens_n = None
    closes_n = None
    pnl_summary, pnl_path = _load_pnl_summary(repo_root)
    if pnl_summary:
        net_pnl = pnl_summary.get("net_pnl")
        opens_n = pnl_summary.get("opens_n") or pnl_summary.get("open_n")
        closes_n = pnl_summary.get("closes_n") or pnl_summary.get("close_n")
    else:
        total, opens, closes = _summarize_trade_journal(repo_root)
        if total is not None:
            opens_n = opens
            closes_n = closes
    if net_pnl is None:
        missing_reasons["net_pnl"] = "paper_pnl_summary.json missing"

    def _rate(numerator: Optional[int], denominator: Optional[int]) -> float:
        if numerator is None or denominator is None:
            return 0.0
        if denominator <= 0:
            return 0.0
        return float(numerator) / float(denominator)

    eval_denom = evaluated_n
    if eval_denom is None:
        eval_denom = universe_size
    signal_rate = _rate(signaled_n or 0, eval_denom or 0)

    http_total = None
    if exec_evidence_http_200_n is not None or exec_evidence_http_error_n is not None:
        http_total = (exec_evidence_http_200_n or 0) + (exec_evidence_http_error_n or 0)
    http_success_rate = _rate(exec_evidence_http_200_n or 0, http_total or 0)
    error_rate = _rate(exec_evidence_http_error_n or 0, http_total or 0)

    summary = {
        "run_tag": run_tag,
        "run_id": run_id_value,
        "run_id_source": run_id_source,
        "run_id_confidence": run_id_confidence,
        "mode": mode,
        "run_mode": run_mode,
        "dry_run": dry_run,
        "paper_trading": paper_trading,
        "universe_size": universe_size,
        "candidates_written_n": candidates_written_n,
        "exec_evidence_http_200_n": exec_evidence_http_200_n,
        "exec_evidence_http_error_n": exec_evidence_http_error_n,
        "ev_nonempty_n": ev_nonempty_n,
        "fair_yes_nonempty_n": fair_yes_nonempty_n,
        "allowed_to_trade_n": allowed_to_trade_n,
        "evaluated_n": evaluated_n,
        "signaled_n": signaled_n,
        "paper_open_attempted_n": paper_open_attempted_n,
        "processed_n": processed_n,
        "approved_n": approved_n,
        "rejected_n": rejected_n,
        "holds_n": holds_n,
        "demo_alpha_mode": demo_alpha_mode,
        "demo_edge_bps": demo_edge_bps,
        "demo_max_spread_bps": demo_max_spread_bps,
        "rest_avg_ms": rest_avg_ms,
        "rest_p95_ms": rest_p95_ms,
        "ws_age_seconds": ws_age_seconds,
        "ws_status": ws_status,
        "market_fetch_ok_n": market_fetch_ok_n,
        "market_fetch_err_n": market_fetch_err_n,
        "book_fetch_ok_n": book_fetch_ok_n,
        "book_fetch_err_n": book_fetch_err_n,
        "signal_rate": signal_rate,
        "http_success_rate": http_success_rate,
        "error_rate": error_rate,
        "net_pnl": net_pnl,
        "opens_n": opens_n,
        "closes_n": closes_n,
        "missing_reasons": missing_reasons,
        "artifacts": {
            "pipeline_status": str(repo_root / "reports" / "pipeline_status.json"),
            "polymarket_log": str(repo_root / "logs" / "polymarket.log"),
            "candidates_csv": str(candidates_csv) if candidates_csv else None,
            "paper_pnl_summary": str(pnl_path) if pnl_summary else None,
        },
    }

    if output_dir is None:
        output_dir = run_dir
    ensure_dir(output_dir)
    output_path = Path(output_dir) / "summary.json"
    write_json(output_path, summary)

    if run_id_value:
        run_id_dir = repo_root / "out" / "evolution" / str(run_id_value)
        if Path(output_dir).resolve() != run_id_dir.resolve():
            ensure_dir(run_id_dir)
            write_json(run_id_dir / "summary.json", summary)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a run from logs and reports.")
    parser.add_argument("--run-tag", required=True, help="baseline or candidate")
    parser.add_argument("--run-dir", required=True, help="Directory containing stdout/stderr")
    parser.add_argument("--repo-root", default=".", help="Repo root")
    parser.add_argument("--run-id", default="", help="Optional run_id override")
    parser.add_argument("--output-dir", default="", help="Output directory for summary")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    repo_root = Path(args.repo_root)
    run_id = args.run_id or None
    output_dir = Path(args.output_dir) if args.output_dir else None

    output_path = summarize_run(
        run_tag=args.run_tag,
        run_dir=run_dir,
        repo_root=repo_root,
        run_id=run_id,
        output_dir=output_dir,
    )
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
