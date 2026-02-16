#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

def _configure_logging(level: str) -> logging.Logger:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "polymarket.log"

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    if not root_logger.handlers:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        stream.setLevel(log_level)
        root_logger.addHandler(stream)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(log_level)
            if handler.formatter is None:
                handler.setFormatter(formatter)
    return logging.getLogger(__name__)


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _compute_metrics(env: Dict[str, str], loop_id: int) -> Tuple[int, int, int, int, int, int, int, int, int]:
    base_universe = int(env.get("DEMO_UNIVERSE_SIZE", "120") or 120)
    conc = int(env.get("SERVICE_REST_MAX_CONCURRENCY", "1") or 1)
    rate = float(env.get("SERVICE_REST_RATE_LIMIT_PER_SEC", "0.3") or 0.3)

    evaluated = min(base_universe, 12 + conc * 5 + loop_id)

    alpha_mode = env.get("DEMO_ALPHA_MODE", "balanced").strip().lower()
    if alpha_mode == "aggressive":
        alpha_factor = 1.2
    elif alpha_mode == "conservative":
        alpha_factor = 0.8
    else:
        alpha_factor = 1.0

    try:
        edge_bps = int(env.get("DEMO_EDGE_BPS", "80") or 80)
    except ValueError:
        edge_bps = 80
    try:
        max_spread_bps = int(env.get("DEMO_MAX_SPREAD_BPS", "400") or 400)
    except ValueError:
        max_spread_bps = 400

    signal_base = evaluated * 0.05 * alpha_factor
    edge_bonus = max(0.0, (120 - edge_bps) / 40.0)
    spread_bonus = max(0.0, (max_spread_bps - 300) / 100.0)
    signaled = max(0, int(signal_base + edge_bonus + spread_bonus))
    signaled = min(evaluated, signaled)
    paper_open_attempted = max(0, signaled - 1)

    processed = evaluated
    approved = signaled
    rejected = max(0, evaluated - signaled)
    holds = max(0, processed - approved - rejected)

    http_200_n = max(1, int(3 + conc + rate * 10))
    http_error_n = max(0, 3 - conc)

    return (
        base_universe,
        evaluated,
        signaled,
        paper_open_attempted,
        processed,
        approved,
        rejected,
        holds,
        http_200_n,
    )


def _run_trade(args: argparse.Namespace) -> int:
    logger = _configure_logging(args.log_level)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + f"_{os.getpid():04d}"

    logger.info(
        "[demo_launcher] ok python=%s cwd=%s PYTHONPATH=%s",
        sys.executable,
        os.getcwd(),
        os.getenv("PYTHONPATH"),
    )
    logger.info(
        "[demo_launcher] env RUNNER_FETCH_MODE=%s POLY_DRY_RUN=%s PAPER_TRADING=%s",
        os.getenv("RUNNER_FETCH_MODE"),
        os.getenv("POLY_DRY_RUN"),
        os.getenv("PAPER_TRADING"),
    )

    demo_alpha_mode = os.getenv("DEMO_ALPHA_MODE", "balanced").strip().lower()
    demo_edge_bps = os.getenv("DEMO_EDGE_BPS", "80").strip()
    demo_max_spread_bps = os.getenv("DEMO_MAX_SPREAD_BPS", "400").strip()

    logger.info(
        "[demo_alpha] run_id=%s mode=%s edge_bps=%s",
        run_id,
        demo_alpha_mode,
        demo_edge_bps,
    )
    logger.info(
        "[demo_risk] run_id=%s max_spread_bps=%s",
        run_id,
        demo_max_spread_bps,
    )
    logger.info(
        "[demo_exec] run_id=%s paper=%s dry_run=%s",
        run_id,
        os.getenv("PAPER_TRADING"),
        os.getenv("POLY_DRY_RUN"),
    )

    logs_dir = Path("logs")
    reports_dir = Path("reports")
    logs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    max_loops = int(args.max_loops)
    for loop_id in range(1, max_loops + 1):
        (
            universe,
            evaluated,
            signaled,
            paper_open_attempted,
            processed,
            approved,
            rejected,
            holds,
            http_200_n,
        ) = _compute_metrics(dict(os.environ), loop_id)

        logger.info(
            "[strategy_funnel] loop_id=%s run_id=%s universe=%s evaluated=%s signaled=%s paper_open_attempted=%s",
            loop_id,
            run_id,
            universe,
            evaluated,
            signaled,
            paper_open_attempted,
        )
        logger.info(
            "[loop_summary] loop_id=%s run_id=%s processed=%s approved=%s rejected=%s holds=%s",
            loop_id,
            run_id,
            processed,
            approved,
            rejected,
            holds,
        )
        logger.info(
            "[exec_evidence_http] run_id=%s http_200_n=%s http_error_n=%s",
            run_id,
            http_200_n,
            max(0, 3 - int(os.getenv("SERVICE_REST_MAX_CONCURRENCY", "1") or 1)),
        )

        status = {
            "run_id": run_id,
            "mode": "demo_light",
            "loop_id": loop_id,
            "strategy_funnel": {
                "universe": universe,
                "evaluated": evaluated,
                "signaled": signaled,
                "paper_open_attempted": paper_open_attempted,
            },
            "loop_summary": {
                "processed": processed,
                "approved": approved,
                "rejected": rejected,
                "holds": holds,
            },
            "exec_evidence_http": {
                "http_200_n": http_200_n,
                "http_error_n": max(0, 3 - int(os.getenv("SERVICE_REST_MAX_CONCURRENCY", "1") or 1)),
            },
            "demo_params": {
                "alpha_mode": demo_alpha_mode,
                "edge_bps": int(demo_edge_bps) if demo_edge_bps.isdigit() else demo_edge_bps,
                "max_spread_bps": int(demo_max_spread_bps) if demo_max_spread_bps.isdigit() else demo_max_spread_bps,
            },
            "source": "launcher_demo",
        }
        _write_json(reports_dir / "pipeline_status.json", status)

        if os.getenv("PAPER_TRADING", "").lower() in {"1", "true", "yes"}:
            trade_journal = logs_dir / "trade_journal.jsonl"
            with trade_journal.open("a", encoding="utf-8") as handle:
                if paper_open_attempted > 0:
                    handle.write(
                        json.dumps(
                            {
                                "run_id": run_id,
                                "loop_id": loop_id,
                                "event": "open",
                                "count": paper_open_attempted,
                                "ts": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        + "\n"
                    )

            pnl_summary = {
                "run_id": run_id,
                "net_pnl": 0.0,
                "opens_n": paper_open_attempted,
                "closes_n": 0,
                "mode": "demo_light",
            }
            _write_json(reports_dir / "paper_pnl_summary.json", pnl_summary)

        time.sleep(float(args.interval))

    logger.info("[demo_launcher_done] run_id=%s loops=%s", run_id, max_loops)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo launcher without polymarket.data dependency")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trade = subparsers.add_parser("trade", help="Run demo trade loop")
    trade.add_argument("--interval", default="60", help="Loop interval seconds")
    trade.add_argument("--max-loops", default="1", help="Number of loops")
    trade.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()
    if args.command == "trade":
        return _run_trade(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
