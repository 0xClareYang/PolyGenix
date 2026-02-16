from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.config_store import load_config_layers, load_env_file, write_env
from tools.evolution.guardian_alerts import emit_alert

CN_TZ = timezone(timedelta(hours=8))


@dataclass
class RestartPolicy:
    max_per_hour: int
    stagnation_secs: int
    heartbeat_secs: int


def should_restart(last_heartbeat_ts: float, last_log_ts: float, now_ts: float, stagnation_secs: int) -> bool:
    if last_heartbeat_ts and now_ts - last_heartbeat_ts > stagnation_secs:
        return True
    if last_log_ts and now_ts - last_log_ts > stagnation_secs:
        return True
    return False


def prune_restart_times(times: List[float], now_ts: float, window_secs: int = 3600) -> List[float]:
    return [t for t in times if now_ts - t <= window_secs]


def freeze_state(state_path: Path, reason: str) -> dict:
    payload = {}
    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    payload["frozen"] = True
    payload["freeze_reason"] = reason
    payload["failure_streak"] = max(int(payload.get("failure_streak") or 0), 3)
    payload["freeze_ts"] = datetime.now(CN_TZ).isoformat()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _log(path: Path, message: str) -> None:
    line = f"[{datetime.now(CN_TZ).isoformat()}] {message}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line)


def _write_heartbeat(path: Path, status: str, pid: Optional[int], loop_id: int) -> None:
    payload = {
        "ts": datetime.now(CN_TZ).isoformat(),
        "status": status,
        "pid": pid,
        "loop_id": loop_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _log_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _run_child(python_bin: str, module: str, interval: str, max_loops: str, env: dict, stdout_path: Path, stderr_path: Path) -> subprocess.Popen:
    cmd = [
        python_bin,
        "-u",
        "-m",
        module,
        "trade",
        "--interval",
        interval,
        "--log-level",
        "INFO",
        "--max-loops",
        max_loops,
    ]
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("a", encoding="utf-8")
    stderr_handle = stderr_path.open("a", encoding="utf-8")
    return subprocess.Popen(cmd, env=env, stdout=stdout_handle, stderr=stderr_handle)


def run_guardian(args: argparse.Namespace) -> int:
    logs_dir = Path("logs")
    reports_dir = Path("reports")
    logs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    out_dir = Path(args.output_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    heartbeat_path = Path(args.heartbeat_path)
    status_path = Path(args.status_path)
    night_log = Path(args.night_log)

    policy = RestartPolicy(
        max_per_hour=int(os.environ.get("GUARDIAN_MAX_RESTARTS_PER_HOUR", "3")),
        stagnation_secs=int(os.environ.get("GUARDIAN_STAGNATION_SECS", "180")),
        heartbeat_secs=int(os.environ.get("GUARDIAN_HEARTBEAT_SECS", "10")),
    )

    interval = os.environ.get("GUARDIAN_INTERVAL_SECS", "60")
    max_loops = int(os.environ.get("GUARDIAN_MAX_LOOPS", "0"))

    env = os.environ.copy()
    env.update(load_config_layers("."))
    if os.environ.get("ENABLE_LIVE_TRADING") != "1":
        env["POLY_DRY_RUN"] = "true"
        env["PAPER_TRADING"] = "1"

    python_bin = os.environ.get("PYTHON_BIN", ".venv/bin/python")
    if not Path(python_bin).exists():
        python_bin = sys.executable
    launcher_module = args.launcher

    restart_times: List[float] = []
    loop_id = 0
    unhealthy_streak = 0
    max_unhealthy = int(os.environ.get("GUARDIAN_MAX_UNHEALTHY", "3"))

    while True:
        loop_id += 1
        _log(night_log, f"guardian loop start {loop_id}")
        child = _run_child(
            python_bin,
            launcher_module,
            interval,
            "1",
            env,
            out_dir / "guardian_stdout.log",
            out_dir / "guardian_stderr.log",
        )

        last_log_ts = _log_mtime(logs_dir / "polymarket.log")
        last_heartbeat = time.time()
        restart_flag = False

        while child.poll() is None:
            now_ts = time.time()
            _write_heartbeat(heartbeat_path, "running", child.pid, loop_id)
            last_heartbeat = now_ts
            current_log_ts = _log_mtime(logs_dir / "polymarket.log")
            if current_log_ts != last_log_ts:
                last_log_ts = current_log_ts
            if should_restart(last_heartbeat, last_log_ts, now_ts, policy.stagnation_secs):
                _log(night_log, "stagnation detected; restarting child")
                restart_flag = True
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                break
            time.sleep(policy.heartbeat_secs)

        exit_code = child.poll() or 0
        if exit_code != 0 or restart_flag:
            restart_times.append(time.time())
            restart_times = prune_restart_times(restart_times, time.time())
            _log(night_log, f"child exit={exit_code} restart_count={len(restart_times)}")

        if len(restart_times) >= policy.max_per_hour:
            state_path = Path("out/evolution/state.json")
            freeze_state(state_path, "guardian restart limit exceeded")
            status_payload = {
                "status": "frozen",
                "reason": "restart_limit",
                "restart_count": len(restart_times),
                "loop_id": loop_id,
                "ts": datetime.now(CN_TZ).isoformat(),
            }
            status_path.write_text(json.dumps(status_payload, indent=2, sort_keys=True), encoding="utf-8")
            emit_alert(
                "guardian freeze: restart limit exceeded",
                "ERROR",
                Path("out/guardian/alerts.jsonl"),
                status_payload,
            )
            _log(night_log, "freeze applied; guardian exiting")
            return 1

        # Run guardian health (subprocess to avoid argparse conflicts)
        subprocess.run(
            [
                python_bin,
                "tools/evolution/guardian_health.py",
                "--output-dir",
                str(out_dir),
            ],
            check=False,
            env=env,
        )

        health_path = Path("out/guardian/health.json")
        if health_path.exists():
            try:
                health = json.loads(health_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                health = {}
            if health.get("healthy") is False:
                unhealthy_streak += 1
                emit_alert(
                    "guardian unhealthy",
                    "WARN",
                    Path("out/guardian/alerts.jsonl"),
                    health,
                )
            else:
                unhealthy_streak = 0

        if unhealthy_streak >= max_unhealthy:
            state_path = Path("out/evolution/state.json")
            freeze_state(state_path, "guardian unhealthy streak")
            cfg_dir = Path("config") / "evolution"
            last_good = load_env_file(cfg_dir / "last_good.env")
            if last_good:
                write_env(cfg_dir / "current.env", last_good)
            status_payload = {
                "status": "frozen",
                "reason": "unhealthy_streak",
                "unhealthy_streak": unhealthy_streak,
                "loop_id": loop_id,
                "ts": datetime.now(CN_TZ).isoformat(),
            }
            status_path.write_text(json.dumps(status_payload, indent=2, sort_keys=True), encoding="utf-8")
            emit_alert(
                "guardian freeze: unhealthy streak",
                "ERROR",
                Path("out/guardian/alerts.jsonl"),
                status_payload,
            )
            _log(night_log, "freeze applied; guardian exiting due to unhealthy streak")
            return 1

        status_payload = {
            "status": "ok",
            "restart_count": len(restart_times),
            "loop_id": loop_id,
            "ts": datetime.now(CN_TZ).isoformat(),
        }
        status_path.write_text(json.dumps(status_payload, indent=2, sort_keys=True), encoding="utf-8")

        if max_loops and loop_id >= max_loops:
            break
        time.sleep(int(interval))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Guardian runner with restart policy.")
    parser.add_argument("--output-root", default="out/guardian", help="Output root")
    parser.add_argument("--heartbeat-path", default="out/guardian/heartbeat.json", help="Heartbeat path")
    parser.add_argument("--status-path", default="out/guardian/last_status.json", help="Last status path")
    parser.add_argument("--night-log", default="out/guardian/night_run.log", help="Night log path")
    parser.add_argument("--launcher", default="apps.launcher_demo", help="Launcher module")
    args = parser.parse_args()

    return run_guardian(args)


if __name__ == "__main__":
    raise SystemExit(main())
