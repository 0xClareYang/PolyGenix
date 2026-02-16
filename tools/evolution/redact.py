from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

SENSITIVE_KEYS = [
    "api_key",
    "secret",
    "passphrase",
    "token",
    "private_key",
    "wallet",
    "password",
    "mnemonic",
    "seed",
]

PATTERN = re.compile(r"(?i)(%s)\s*[:=]\s*([^\s,;]+)" % "|".join(SENSITIVE_KEYS))


def redact_text(text: str) -> str:
    return PATTERN.sub(r"\1=<redacted>", text)


def redact_lines(lines: Iterable[str]) -> str:
    return "\n".join(redact_text(line) for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Redact sensitive tokens from text.")
    parser.add_argument("--in", dest="input_path", default="", help="Input file path")
    parser.add_argument("--out", dest="output_path", default="", help="Output file path")
    args = parser.parse_args()

    if not args.input_path:
        return 1

    path = Path(args.input_path)
    if not path.exists():
        return 2

    text = path.read_text(encoding="utf-8", errors="replace")
    redacted = redact_text(text)

    if args.output_path:
        out_path = Path(args.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(redacted, encoding="utf-8")
        return 0

    print(redacted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
