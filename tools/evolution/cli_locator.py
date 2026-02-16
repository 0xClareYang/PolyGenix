from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]


def _is_executable(path: Optional[str]) -> bool:
    if not path:
        return False
    candidate = Path(path)
    return candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK)


def _first_executable(paths: list[Optional[str]]) -> Optional[str]:
    for path in paths:
        if _is_executable(path):
            return path
    return None


def _read_wrapper_path(repo_root: Path) -> Optional[str]:
    wrapper_path = repo_root / "out" / "evolution" / "runtime_probe" / "lobster_wrapper_path.txt"
    if not wrapper_path.exists():
        return None
    text = wrapper_path.read_text(encoding="utf-8", errors="replace").strip()
    return text or None


def _check_lobster_subcommand(runtime_cli_path: str) -> bool:
    try:
        proc = subprocess.run(
            [runtime_cli_path, "lobster", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        output = f"{proc.stdout}\n{proc.stderr}".lower()
        if proc.returncode != 0:
            return False
        if "lobster" not in output:
            return False
        if "unknown command" in output or "not found" in output or "unrecognized" in output:
            return False
        return True
    except OSError:
        return False


def locate_cli(env: Optional[Dict[str, str]] = None, repo_root: Optional[Path] = None) -> Dict[str, str]:
    env = env or dict(os.environ)
    repo_root = repo_root or REPO_ROOT

    runtime_env_order = [
        ("runtime_cli_bin", env.get("RUNTIME_CLI_BIN")),
        ("openclaw_bin", env.get("OPENCLAW_BIN")),
        ("moltbot_bin", env.get("MOLTBOT_BIN")),
        ("clawdbot_bin", env.get("CLAWDBOT_BIN")),
        ("claw_bin", env.get("CLAW_BIN")),
    ]

    runtime_cli_path = _first_executable([path for _, path in runtime_env_order])
    runtime_cli_source = "env"

    if not runtime_cli_path:
        for name in ("openclaw", "moltbot", "clawdbot", "claw"):
            found = shutil.which(name)
            if found:
                runtime_cli_path = found
                runtime_cli_source = "path"
                break

    venv_bin = repo_root / ".venv" / "bin"
    if not runtime_cli_path:
        for name in ("openclaw", "moltbot", "clawdbot", "claw"):
            candidate = venv_bin / name
            if _is_executable(str(candidate)):
                runtime_cli_path = str(candidate)
                runtime_cli_source = "venv"
                break

    runtime_cli_name = Path(runtime_cli_path).name if runtime_cli_path else "missing"

    lobster_env_paths = [
        env.get("LOBSTER_BIN"),
        env.get("EVOLVE_LOBSTER_PATH"),
    ]
    lobster_path = _first_executable(lobster_env_paths)
    lobster_source = "env"

    if not lobster_path:
        wrapper_path = _read_wrapper_path(repo_root)
        if wrapper_path and _is_executable(wrapper_path):
            lobster_path = wrapper_path
            lobster_source = "wrapper"

    if not lobster_path:
        found = shutil.which("lobster")
        if found:
            lobster_path = found
            lobster_source = "path"

    if not lobster_path:
        candidate = venv_bin / "lobster"
        if _is_executable(str(candidate)):
            lobster_path = str(candidate)
            lobster_source = "venv"

    lobster_mode = "missing"
    if lobster_path:
        lobster_mode = "standalone"
    elif runtime_cli_path and _check_lobster_subcommand(runtime_cli_path):
        lobster_mode = "subcommand"
        lobster_path = runtime_cli_path
        lobster_source = "runtime_subcommand"

    return {
        "runtime_cli_name": runtime_cli_name,
        "runtime_cli_path": runtime_cli_path or "",
        "runtime_cli_source": runtime_cli_source if runtime_cli_path else "missing",
        "lobster_mode": lobster_mode,
        "lobster_path": lobster_path or "",
        "lobster_source": lobster_source if lobster_path else "missing",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve runtime CLI and lobster CLI paths.")
    parser.add_argument("--json-out", default="", help="Optional path to write JSON output.")
    args = parser.parse_args()

    data = locate_cli()
    payload = json.dumps(data, indent=2, sort_keys=True)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
