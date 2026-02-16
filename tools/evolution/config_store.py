from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional


DEFAULTS: Dict[str, str] = {
    "RUNNER_FETCH_MODE": "light",
    "POLY_DRY_RUN": "true",
    "PAPER_TRADING": "1",
    "ONE_LOOP": "1",
    "SKIP_FETCH_PREFLIGHT": "1",
    "SERVICE_REST_MAX_CONCURRENCY": "1",
    "SERVICE_REST_RATE_LIMIT_PER_SEC": "0.3",
    "NEWS_FORCE_REFRESH": "0",
    "NEWS_BOOTSTRAP_TTL_SECS": "600",
    "NEWS_BOOTSTRAP_TIMEOUT_SECS": "30",
    "DEMO_ALPHA_MODE": "balanced",
    "DEMO_EDGE_BPS": "80",
    "DEMO_MAX_SPREAD_BPS": "400",
}


def _parse_env_lines(lines: Iterable[str]) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def load_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return _parse_env_lines(text.splitlines())


def write_env(path: Path, data: Dict[str, str]) -> None:
    lines = [f"{key}={data[key]}" for key in sorted(data.keys())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_config_layers(repo_root: Path | str = ".") -> Dict[str, str]:
    repo_root = Path(repo_root)
    base = dict(DEFAULTS)

    cfg_dir = repo_root / "config" / "evolution"
    current = load_env_file(cfg_dir / "current.env")
    overrides = load_env_file(cfg_dir / "overrides.env")

    merged = dict(base)
    merged.update(current)
    merged.update(overrides)
    return merged


def sync_from_state_json(repo_root: Path | str = ".") -> Optional[Path]:
    repo_root = Path(repo_root)
    state_path = repo_root / "out" / "evolution" / "state.json"
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    best_config = payload.get("best_config")
    if not isinstance(best_config, dict):
        return None

    cfg_dir = repo_root / "config" / "evolution"
    best_env = cfg_dir / "best.env"
    write_env(best_env, {str(k): str(v) for k, v in best_config.items()})
    return best_env


def promote_candidate(candidate_env: Dict[str, str], repo_root: Path | str = ".") -> Path:
    repo_root = Path(repo_root)
    cfg_dir = repo_root / "config" / "evolution"
    current_path = cfg_dir / "current.env"
    last_good_path = cfg_dir / "last_good.env"

    if current_path.exists():
        last_good_path.write_text(current_path.read_text(encoding="utf-8"), encoding="utf-8")

    write_env(current_path, {str(k): str(v) for k, v in candidate_env.items()})
    return current_path

