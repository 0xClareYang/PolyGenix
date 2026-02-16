from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def safe_load_json(path: str | Path) -> Optional[Dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return None
    try:
        return json.loads(read_text(target))
    except json.JSONDecodeError:
        return None


def write_json(path: str | Path, obj: Any) -> None:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(
        json.dumps(obj, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_subprocess(
    cmd: list[str],
    env: Dict[str, str],
    stdout_path: str | Path,
    stderr_path: str | Path,
) -> int:
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    ensure_dir(stdout_path.parent)
    ensure_dir(stderr_path.parent)
    with open(stdout_path, "wb") as stdout_f, open(stderr_path, "wb") as stderr_f:
        proc = subprocess.run(cmd, env=env, stdout=stdout_f, stderr=stderr_f)
    return proc.returncode
