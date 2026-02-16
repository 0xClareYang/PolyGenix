from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import read_text
from tools.evolution.config_store import load_env_file, write_env

RE_HTTP_200 = re.compile(r"http_200_n=(\d+)")
RE_HTTP_ERROR = re.compile(r"http_error_n=(\d+)")
RE_STRATEGY_EVALUATED = re.compile(r"evaluated=(\d+)")
RE_STRATEGY_SIGNALED = re.compile(r"signaled=(\d+)")
RE_STRATEGY_UNIVERSE = re.compile(r"universe=(\d+)")
RE_LOOP = re.compile(r"loop_id=(\d+)")
RE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")


@dataclass
class HealthThresholds:
    min_http_success: float
    max_error_rate: float
    min_signal_rate: float


def _parse_timestamp(line: str) -> Optional[datetime]:
    match = RE_TS.search(line)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iter_recent_lines(text: str, window_minutes: int) -> Iterable[str]:
    if window_minutes <= 0:
        yield from text.splitlines()
        return
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    for line in text.splitlines():
        ts = _parse_timestamp(line)
        if ts is None or ts >= cutoff:
            yield line


def parse_logs(paths: Iterable[Path], window_minutes: int) -> Dict[str, int]:
    metrics: Dict[str, int] = {}
    loop_ids = set()
    for path in paths:
        if not path.exists():
            continue
        text = read_text(path)
        for line in _iter_recent_lines(text, window_minutes):
            if "exec_evidence_http" in line:
                match = RE_HTTP_200.search(line)
                if match:
                    metrics["http_200_n"] = int(match.group(1))
                match = RE_HTTP_ERROR.search(line)
                if match:
                    metrics["http_error_n"] = int(match.group(1))
            if "[strategy_funnel]" in line:
                match = RE_STRATEGY_EVALUATED.search(line)
                if match:
                    metrics["evaluated_n"] = int(match.group(1))
                match = RE_STRATEGY_SIGNALED.search(line)
                if match:
                    metrics["signaled_n"] = int(match.group(1))
                match = RE_STRATEGY_UNIVERSE.search(line)
                if match:
                    metrics["universe_n"] = int(match.group(1))
            match = RE_LOOP.search(line)
            if match:
                loop_ids.add(match.group(1))
    if loop_ids:
        metrics["loop_count"] = len(loop_ids)
    return metrics


def load_pipeline_metrics(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    ws_age = data.get("ws_age_seconds")
    rest_p95 = data.get("rest_p95_ms") or data.get("rest_latency_p95_ms")
    return {
        "ws_age_seconds": float(ws_age) if ws_age is not None else None,
        "rest_p95_ms": float(rest_p95) if rest_p95 is not None else None,
    }


def compute_rates(metrics: Dict[str, int]) -> Dict[str, float]:
    http_200 = metrics.get("http_200_n", 0)
    http_err = metrics.get("http_error_n", 0)
    http_total = http_200 + http_err
    http_success_rate = (http_200 / http_total) if http_total > 0 else 0.0
    error_rate = (http_err / http_total) if http_total > 0 else 0.0

    evaluated = metrics.get("evaluated_n") or metrics.get("universe_n") or 0
    signaled = metrics.get("signaled_n", 0)
    signal_rate = (signaled / evaluated) if evaluated > 0 else 0.0

    return {
        "http_success_rate": http_success_rate,
        "error_rate": error_rate,
        "signal_rate": signal_rate,
    }


def evaluate_health(rates: Dict[str, float], thresholds: HealthThresholds) -> Tuple[bool, Dict[str, str]]:
    reasons: Dict[str, str] = {}
    if rates["http_success_rate"] < thresholds.min_http_success:
        reasons["http_success_rate"] = f"{rates['http_success_rate']:.3f} < {thresholds.min_http_success}"
    if rates["error_rate"] > thresholds.max_error_rate:
        reasons["error_rate"] = f"{rates['error_rate']:.3f} > {thresholds.max_error_rate}"
    if rates["signal_rate"] < thresholds.min_signal_rate:
        reasons["signal_rate"] = f"{rates['signal_rate']:.3f} < {thresholds.min_signal_rate}"
    return (len(reasons) == 0), reasons


def recommended_patch(rates: Dict[str, float]) -> Dict[str, str]:
    patch = {
        "SERVICE_REST_MAX_CONCURRENCY": "1",
        "SERVICE_REST_RATE_LIMIT_PER_SEC": "0.3",
    }
    if rates.get("http_success_rate", 1.0) < 0.5 or rates.get("error_rate", 0.0) > 0.2:
        patch["SERVICE_USE_WS"] = "false"
    return patch


def main() -> int:
    parser = argparse.ArgumentParser(description="Guardian health evaluator.")
    parser.add_argument("--log", action="append", default=[], help="Log file path (repeatable)")
    parser.add_argument("--pipeline", default="reports/pipeline_status.json", help="Pipeline status JSON")
    parser.add_argument("--output-dir", default="out/guardian", help="Output dir")
    parser.add_argument("--window-mins", default="30", help="Window minutes to consider")
    parser.add_argument("--auto-mitigate", action="store_true", help="Apply mitigation to overrides.env")
    parser.add_argument("--overrides-env", default="config/evolution/overrides.env")
    args = parser.parse_args()

    window_minutes = int(args.window_mins)
    logs = [Path(p) for p in args.log] if args.log else [Path("logs/polymarket.log")]
    metrics = parse_logs(logs, window_minutes)
    rates = compute_rates(metrics)

    thresholds = HealthThresholds(
        min_http_success=float(os.getenv("GUARDIAN_MIN_HTTP_SUCCESS", "0.85")),
        max_error_rate=float(os.getenv("GUARDIAN_MAX_ERROR_RATE", "0.10")),
        min_signal_rate=float(os.getenv("GUARDIAN_MIN_SIGNAL_RATE", "0.01")),
    )

    healthy, reasons = evaluate_health(rates, thresholds)
    pipeline_metrics = load_pipeline_metrics(Path(args.pipeline))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    health_payload = {
        "healthy": healthy,
        "reasons": reasons,
        "metrics": metrics,
        "rates": rates,
        "thresholds": {
            "min_http_success": thresholds.min_http_success,
            "max_error_rate": thresholds.max_error_rate,
            "min_signal_rate": thresholds.min_signal_rate,
        },
        "pipeline": pipeline_metrics,
        "window_minutes": window_minutes,
    }

    health_path = out_dir / "health.json"
    health_path.write_text(json.dumps(health_payload, indent=2, sort_keys=True), encoding="utf-8")

    if not healthy:
        patch = recommended_patch(rates)
        alert_path = out_dir / "alerts.md"
        lines = [
            "# Guardian Alert",
            "",
            f"- time: {datetime.now(timezone.utc).isoformat()}",
            f"- healthy: {healthy}",
            "",
            "## Reasons",
        ]
        for key, value in reasons.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
        lines.append("## Recommended Patch")
        for key, value in patch.items():
            lines.append(f"- {key}={value}")
        alert_path.write_text("\n".join(lines), encoding="utf-8")

        if args.auto_mitigate or os.getenv("GUARDIAN_AUTO_MITIGATE") == "1":
            overrides_path = Path(args.overrides_env)
            overrides = load_env_file(overrides_path)
            overrides.update(patch)
            write_env(overrides_path, overrides)

    print(str(health_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
