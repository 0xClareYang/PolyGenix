from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import request


def emit_alert(message: str, level: str, output_path: Path, context: Optional[Dict[str, Any]] = None) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")

    ntfy_url = os.environ.get("NTFY_URL")
    if ntfy_url:
        try:
            req = request.Request(ntfy_url, data=message.encode("utf-8"), method="POST")
            request.urlopen(req, timeout=5)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Guardian alerts writer.")
    parser.add_argument("--message", required=True, help="Alert message")
    parser.add_argument("--level", default="WARN", help="Alert level")
    parser.add_argument("--output", default="out/guardian/alerts.jsonl", help="Output JSONL")
    parser.add_argument("--context", default="", help="Optional JSON context")
    args = parser.parse_args()

    context = None
    if args.context:
        try:
            context = json.loads(args.context)
        except json.JSONDecodeError:
            context = {"raw": args.context}

    emit_alert(args.message, args.level, Path(args.output), context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
