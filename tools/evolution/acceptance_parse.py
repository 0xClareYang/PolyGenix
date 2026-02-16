from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict

LINE_RE = re.compile(r"compare_md_path=([^ ]+)\s+baseline_run_id=([^ ]+)\s+candidate_run_id=([^ ]+)")
RESULT_LINE_RE = re.compile(r"result_line_path=([^ ]+)")


def find_compare_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if "compare_md_path=" in line:
            return line.strip()
    return ""


def find_result_line_path(text: str) -> str:
    for line in reversed(text.splitlines()):
        if "result_line_path=" not in line:
            continue
        match = RESULT_LINE_RE.search(line)
        if match:
            return match.group(1)
    return ""


def parse_compare_line(line: str) -> Dict[str, str]:
    match = LINE_RE.search(line)
    if not match:
        return {"compare_md_path": "", "baseline_run_id": "", "candidate_run_id": "", "line": line}
    return {
        "compare_md_path": match.group(1),
        "baseline_run_id": match.group(2),
        "candidate_run_id": match.group(3),
        "line": line.strip(),
    }


def parse_from_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {"compare_md_path": "", "baseline_run_id": "", "candidate_run_id": "", "line": ""}
    text = path.read_text(encoding="utf-8", errors="replace")
    result_line_path = find_result_line_path(text)
    if result_line_path:
        data = parse_from_file(Path(result_line_path))
        if data.get("compare_md_path"):
            return data
    line = find_compare_line(text)
    return parse_compare_line(line) if line else {"compare_md_path": "", "baseline_run_id": "", "candidate_run_id": "", "line": ""}


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse compare line from acceptance logs.")
    parser.add_argument("--file", default="", help="Path to log file.")
    parser.add_argument("--result-line", default="", help="Optional result_line.txt path.")
    parser.add_argument("--fields", action="store_true", help="Print fields space-separated.")
    args = parser.parse_args()

    data = {"compare_md_path": "", "baseline_run_id": "", "candidate_run_id": "", "line": ""}
    if args.result_line:
        data = parse_from_file(Path(args.result_line))

    if (not data.get("compare_md_path")) and args.file:
        data = parse_from_file(Path(args.file))

    if args.fields:
        print(
            f"{data.get('compare_md_path','')} {data.get('baseline_run_id','')} {data.get('candidate_run_id','')}")
        return 0

    print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
