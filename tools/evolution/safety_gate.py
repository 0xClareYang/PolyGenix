from __future__ import annotations

import os
import sys
from typing import Dict, Iterable, Tuple

from tools.evolution.redact import redact_text

REQUIRED_TRUE = {
    "POLY_DRY_RUN": {"true", "1", "yes", "on"},
    "PAPER_TRADING": {"true", "1", "yes", "on"},
}

FORBIDDEN_TRUE_KEYS = [
    "ENABLE_LIVE_TRADING",
    "LIVE_TRADING",
    "REAL_TRADING",
    "REAL_ORDERS",
    "PROD_MODE",
    "LIVE_MODE",
]

SUSPECT_KEYS = [
    "PRIVATE_KEY",
    "MNEMONIC",
    "SEED",
    "PASSWORD",
    "PASSPHRASE",
    "API_KEY",
    "SECRET",
]


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize(value: str | None) -> str:
    return str(value).strip().lower() if value is not None else ""


def _detect_suspects(env: Dict[str, str]) -> Iterable[Tuple[str, str]]:
    for key, value in env.items():
        upper = key.upper()
        if any(token in upper for token in SUSPECT_KEYS) and value:
            yield key, value


def assert_dry_run_safety(env: Dict[str, str]) -> None:
    """Fail-closed safety gate for real dry-run launchers.

    Requirements:
      - POLY_DRY_RUN=true
      - PAPER_TRADING=1
      - No live/real/prod flags enabled.
    """
    missing = []
    for key, allowed in REQUIRED_TRUE.items():
        if _normalize(env.get(key)) not in allowed:
            missing.append(key)

    forbidden = [key for key in FORBIDDEN_TRUE_KEYS if _truthy(env.get(key))]

    if missing or forbidden:
        if missing:
            print(f"[safety_gate] missing required flags: {', '.join(missing)}")
        if forbidden:
            print(f"[safety_gate] forbidden live flags enabled: {', '.join(forbidden)}")
        raise SystemExit(42)

    suspects = list(_detect_suspects(env))
    if suspects:
        print("[safety_gate] sensitive variables detected; consider removing or injecting securely.")
        for key, value in suspects:
            print(f"[safety_gate] {key}={redact_text(str(value))}")


def main() -> int:
    try:
        assert_dry_run_safety(dict(os.environ))
    except SystemExit as exc:
        return int(exc.code or 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
