from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evolution.common import safe_load_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Human approval gate for evolution proposals.")
    parser.add_argument("--proposal", required=True, help="Path to proposal.json")
    args = parser.parse_args()

    proposal_path = Path(args.proposal)
    proposal = safe_load_json(proposal_path)
    if proposal is None:
        print(f"[error] proposal not found: {proposal_path}")
        return 1

    env_patch = proposal.get("env_patch", {})
    print("\n[proposal] env_patch")
    for key, value in env_patch.items():
        print(f"- {key}={value}")

    rationale = proposal.get("rationale")
    if rationale:
        print("\n[proposal] rationale")
        if isinstance(rationale, str):
            for line in rationale.splitlines():
                print(f"- {line}")
        else:
            print(f"- {rationale}")

    optional = proposal.get("optional_env_patch", {})
    if optional:
        print("\n[proposal] optional_env_patch (not applied by default)")
        for key, payload in optional.items():
            if isinstance(payload, dict):
                print(f"- {key}={payload.get('value')} enabled={payload.get('enabled')}")
            else:
                print(f"- {key}={payload}")

    safety = proposal.get("safety", {})
    if safety:
        print("\n[proposal] safety")
        for key, value in safety.items():
            print(f"- {key}={value}")

    if os.environ.get("EVOLVE_AUTO_APPROVE") == "1":
        print("\n[approval] EVOLVE_AUTO_APPROVE=1 -> approved")
        return 0

    response = input("\nType APPROVE to continue: ").strip()
    if response == "APPROVE":
        print("[approval] approved")
        return 0

    print("[approval] denied")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
