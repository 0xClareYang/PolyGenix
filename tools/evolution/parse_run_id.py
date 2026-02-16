from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import read_text, write_json

HIGH_RE = re.compile(r"run_id=([0-9]{8}_[0-9]{6}_[0-9]{3,})")
LOW_RE = re.compile(r"run_id=([^ \n]+)")


def _iter_files(paths: Iterable[Path]) -> list[Path]:
    files = [p for p in paths if p.exists() and p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _search_regex(pattern: re.Pattern[str], text: str) -> Optional[str]:
    matches = pattern.findall(text)
    if not matches:
        return None
    return matches[-1]


def extract_run_id(paths: Iterable[Path]) -> Tuple[Optional[str], Optional[str], str]:
    files = _iter_files(paths)
    for path in files:
        text = read_text(path)
        match = _search_regex(HIGH_RE, text)
        if match:
            return match, str(path), "high"
    for path in files:
        text = read_text(path)
        match = _search_regex(LOW_RE, text)
        if match:
            return match, str(path), "low"
    return None, None, "none"


def build_default_paths(root: Path, log_path: Optional[Path]) -> list[Path]:
    paths: list[Path] = []
    if root.exists():
        paths.extend(root.glob("**/*_stdout.log"))
        paths.extend(root.glob("**/*_stderr.log"))
    if log_path is not None:
        paths.append(log_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract run_id from logs.")
    parser.add_argument("--root", default="out/evolution", help="Root to search logs")
    parser.add_argument("--log", default="logs/polymarket.log", help="Main log path")
    parser.add_argument("--output", default="", help="Optional output json path")
    args = parser.parse_args()

    root = Path(args.root)
    log_path = Path(args.log)
    paths = build_default_paths(root, log_path if log_path.exists() else None)
    run_id, source, confidence = extract_run_id(paths)

    payload = {
        "run_id": run_id,
        "source": source,
        "confidence": confidence,
    }

    if args.output:
        write_json(args.output, payload)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
