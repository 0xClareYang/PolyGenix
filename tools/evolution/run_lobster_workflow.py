from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.evolution.common import ensure_dir, read_text, write_json
from tools.evolution.cli_locator import locate_cli


def _is_executable(path: str | None) -> bool:
    if not path:
        return False
    candidate = Path(path)
    return candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK)


def _resolve_cli(runtime_override: str | None, lobster_override: str | None) -> Tuple[str, str | None, str, str | None]:
    data = locate_cli()
    runtime_name = data.get("runtime_cli_name") or "missing"
    runtime_path = data.get("runtime_cli_path") or None
    lobster_mode = data.get("lobster_mode") or "missing"
    lobster_path = data.get("lobster_path") or None

    if runtime_override:
        if _is_executable(runtime_override):
            runtime_path = runtime_override
            runtime_name = Path(runtime_override).name
        else:
            runtime_path = None
            runtime_name = "missing"

    if lobster_override:
        if _is_executable(lobster_override):
            lobster_path = lobster_override
            lobster_mode = "standalone"
        else:
            lobster_path = None
            lobster_mode = "missing"

    if lobster_mode == "subcommand" and not runtime_path:
        lobster_mode = "missing"
        lobster_path = None

    return runtime_name, runtime_path, lobster_mode, lobster_path


def tail_lines(path: Path, limit: int = 50) -> str:
    if not path.exists():
        return ""
    text = read_text(path)
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def _run_capture(
    cmd: list[str],
    env: dict[str, str],
    cwd: str,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def _find_latest_compare(root: Path) -> Optional[Path]:
    candidates = list(root.rglob("compare.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _parse_compare_line(compare_path: Path) -> tuple[str, str, str]:
    baseline = ""
    candidate = ""
    for line in compare_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Baseline run_id:"):
            baseline = line.split(":", 1)[1].strip()
        if line.startswith("Candidate run_id:"):
            candidate = line.split(":", 1)[1].strip()
    return str(compare_path), baseline, candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Lobster workflow via runtime CLI.")
    parser.add_argument(
        "--workflow",
        default="workflows/pm_evolution_demo.lobster",
        help="Path to lobster workflow file.",
    )
    parser.add_argument(
        "--runtime-cli",
        default=None,
        help="Explicit path to runtime CLI (openclaw/moltbot/clawdbot/claw).",
    )
    parser.add_argument(
        "--lobster-bin",
        default=None,
        help="Explicit path to lobster binary (standalone).",
    )
    parser.add_argument(
        "--lobster-path",
        dest="lobster_bin",
        default=None,
        help="Alias for --lobster-bin (explicit lobster path).",
    )
    parser.add_argument(
        "--output-root",
        default="out/evolution/runtime_runs",
        help="Root directory for runtime logs.",
    )
    parser.add_argument(
        "--run-mode",
        default=None,
        help="Optional EVOLVE_RUN_MODE override (demo_light/real_dryrun).",
    )

    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        print(f"[error] workflow not found: {workflow_path}")
        return 2

    runtime_name, runtime_path, lobster_mode, lobster_path = _resolve_cli(
        args.runtime_cli, args.lobster_bin
    )

    if lobster_mode == "missing" or lobster_path is None:
        print("[error] lobster CLI not found. Install or expose it on PATH, then retry.")
        print("[hint] run: command -v claw; claw lobster --help; command -v lobster")
        return 3

    auto_approve = os.environ.get("EVOLVE_AUTO_APPROVE", "1") == "1"
    if lobster_mode == "standalone":
        cmd = [lobster_path, "run", "--mode", "tool", str(workflow_path)]
        runner_desc = "lobster"
    else:
        if runtime_path is None:
            print("[error] runtime CLI missing but lobster subcommand was expected.")
            return 4
        cmd = [runtime_path, "lobster", "run", "--mode", "tool", str(workflow_path)]
        runner_desc = f"{runtime_name} lobster"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir = ensure_dir(Path(args.output_root) / ts)
    stdout_path = out_dir / "runtime_stdout.log"
    stderr_path = out_dir / "runtime_stderr.log"
    resume_stdout_path = out_dir / "runtime_resume_stdout.log"
    resume_stderr_path = out_dir / "runtime_resume_stderr.log"
    result_path = out_dir / "lobster_result.json"
    result_line_path = out_dir / "result_line.txt"

    env = os.environ.copy()
    run_mode = args.run_mode or env.get("EVOLVE_RUN_MODE")
    if run_mode:
        env["EVOLVE_RUN_MODE"] = str(run_mode)

    print(f"[runtime] runner={runner_desc}")
    print(f"[runtime] workflow={workflow_path}")
    print(f"[runtime] stdout={stdout_path}")
    print(f"[runtime] stderr={stderr_path}")

    exit_code, stdout_text, stderr_text = _run_capture(
        cmd,
        env=env,
        cwd=str(REPO_ROOT),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    status = "unknown"
    resume_token = None
    parsed = None
    if stdout_text.strip():
        try:
            parsed = json.loads(stdout_text)
            status = parsed.get("status") or status
            requires = parsed.get("requiresApproval") or {}
            resume_token = requires.get("resumeToken")
        except json.JSONDecodeError:
            status = "invalid_json"

    if exit_code != 0:
        print(f"[error] runtime exited with code {exit_code}")
        stderr_tail = tail_lines(stderr_path)
        stdout_tail = tail_lines(stdout_path)
        if stderr_tail:
            print("[stderr tail]")
            print(stderr_tail)
        if stdout_tail:
            print("[stdout tail]")
            print(stdout_tail)
        write_json(
            result_path,
            {
                "exit_code": exit_code,
                "runner": runner_desc,
                "runtime_cli": runtime_name,
                "runtime_cli_path": runtime_path,
                "lobster_mode": lobster_mode,
                "lobster_path": lobster_path,
                "workflow": str(workflow_path),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "status": status,
                "result_line_path": str(result_line_path),
                "run_mode": run_mode,
            },
        )
        return exit_code

    if status == "needs_approval" and resume_token:
        if not auto_approve:
            print("[runtime] needs approval; set EVOLVE_AUTO_APPROVE=1 to resume automatically.")
            write_json(
                result_path,
                {
                    "exit_code": exit_code,
                    "runner": runner_desc,
                    "runtime_cli": runtime_name,
                    "runtime_cli_path": runtime_path,
                    "lobster_mode": lobster_mode,
                    "lobster_path": lobster_path,
                    "workflow": str(workflow_path),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "status": status,
                    "resume_token": resume_token,
                    "result_line_path": str(result_line_path),
                },
            )
            return 3

        resume_cmd = [lobster_path, "resume", "--token", resume_token, "--approve", "yes"]
        if lobster_mode != "standalone" and runtime_path:
            resume_cmd = [runtime_path, "lobster", "resume", "--token", resume_token, "--approve", "yes"]

        resume_exit, resume_stdout, resume_stderr = _run_capture(
            resume_cmd,
            env=env,
            cwd=str(REPO_ROOT),
            stdout_path=resume_stdout_path,
            stderr_path=resume_stderr_path,
        )
        resume_status = "unknown"
        if resume_stdout.strip():
            try:
                resume_parsed = json.loads(resume_stdout)
                resume_status = resume_parsed.get("status") or resume_status
            except json.JSONDecodeError:
                resume_status = "invalid_json"

        write_json(
            result_path,
            {
                "exit_code": resume_exit,
                "runner": runner_desc,
                "runtime_cli": runtime_name,
                "runtime_cli_path": runtime_path,
                "lobster_mode": lobster_mode,
                "lobster_path": lobster_path,
                "workflow": str(workflow_path),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "resume_stdout_path": str(resume_stdout_path),
                "resume_stderr_path": str(resume_stderr_path),
                "status": status,
                "resume_status": resume_status,
                "resume_token": resume_token,
                "result_line_path": str(result_line_path),
                "run_mode": run_mode,
            },
        )

        if resume_exit != 0 or resume_status != "ok":
            print(f"[error] runtime resume failed (exit={resume_exit}, status={resume_status})")
            return resume_exit or 4

        compare_line = ""
        compare_path = _find_latest_compare(Path("out") / "evolution")
        if compare_path:
            compare_md_path, base_id, cand_id = _parse_compare_line(compare_path)
            compare_line = (
                f"compare_md_path={compare_md_path} "
                f"baseline_run_id={base_id} "
                f"candidate_run_id={cand_id}"
            )
            result_line_path.write_text(compare_line + "\n", encoding="utf-8")

        write_json(
            result_path,
            {
                "exit_code": resume_exit,
                "runner": runner_desc,
                "runtime_cli": runtime_name,
                "runtime_cli_path": runtime_path,
                "lobster_mode": lobster_mode,
                "lobster_path": lobster_path,
                "workflow": str(workflow_path),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "resume_stdout_path": str(resume_stdout_path),
                "resume_stderr_path": str(resume_stderr_path),
                "status": status,
                "resume_status": resume_status,
                "resume_token": resume_token,
                "result_line_path": str(result_line_path),
                "result_line": compare_line,
            },
        )

        print("[runtime] completed successfully after approval")
        if compare_line:
            print(f"result_line_path={result_line_path}")
            print(compare_line)
        return 0

    compare_line = ""
    compare_path = _find_latest_compare(Path("out") / "evolution")
    if compare_path:
        compare_md_path, base_id, cand_id = _parse_compare_line(compare_path)
        compare_line = (
            f"compare_md_path={compare_md_path} "
            f"baseline_run_id={base_id} "
            f"candidate_run_id={cand_id}"
        )
        result_line_path.write_text(compare_line + "\n", encoding="utf-8")

    write_json(
        result_path,
        {
            "exit_code": exit_code,
            "runner": runner_desc,
            "runtime_cli": runtime_name,
            "runtime_cli_path": runtime_path,
            "lobster_mode": lobster_mode,
            "lobster_path": lobster_path,
            "workflow": str(workflow_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "status": status,
            "result_line_path": str(result_line_path),
            "run_mode": run_mode,
            "result_line": compare_line,
        },
    )

    if status == "invalid_json":
        print("[error] lobster output is not valid JSON; expected tool mode.")
        return 5

    print("[runtime] completed successfully")
    if compare_line:
        if run_mode and compare_path:
            try:
                text = compare_path.read_text(encoding="utf-8", errors="replace")
                if f"- baseline: {run_mode}" not in text and f"- candidate: {run_mode}" not in text:
                    print(f"[runtime] warning: compare.md mode does not match EVOLVE_RUN_MODE={run_mode}")
            except Exception:
                pass
        print(f"result_line_path={result_line_path}")
        print(compare_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
