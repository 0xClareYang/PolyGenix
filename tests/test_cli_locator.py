from __future__ import annotations

from pathlib import Path

from tools.evolution.cli_locator import locate_cli


def _make_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_env_override(monkeypatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    runtime = bin_dir / "claw"
    lobster = bin_dir / "lobster"
    _make_exe(runtime, "#!/usr/bin/env bash\necho runtime\n")
    _make_exe(lobster, "#!/usr/bin/env bash\necho lobster\n")

    monkeypatch.setenv("PATH", str(bin_dir))
    data = locate_cli(
        env={"RUNTIME_CLI_BIN": str(runtime), "LOBSTER_BIN": str(lobster)},
        repo_root=tmp_path,
    )

    assert data["runtime_cli_path"] == str(runtime)
    assert data["runtime_cli_name"] == "claw"
    assert data["lobster_mode"] == "standalone"
    assert data["lobster_path"] == str(lobster)


def test_wrapper_path(monkeypatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    lobster = bin_dir / "lobster"
    _make_exe(lobster, "#!/usr/bin/env bash\necho lobster\n")

    wrapper_dir = tmp_path / "out" / "evolution" / "runtime_probe"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    (wrapper_dir / "lobster_wrapper_path.txt").write_text(str(lobster), encoding="utf-8")

    monkeypatch.setenv("PATH", str(bin_dir))
    data = locate_cli(env={}, repo_root=tmp_path)

    assert data["lobster_mode"] == "standalone"
    assert data["lobster_path"] == str(lobster)


def test_subcommand_mode(monkeypatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    runtime = bin_dir / "claw"
    _make_exe(
        runtime,
        "#!/bin/bash\nif [ \"$1\" = \"lobster\" ]; then echo lobster help; exit 0; fi\necho ok\n",
    )

    monkeypatch.setenv("PATH", str(bin_dir))
    data = locate_cli(env={"RUNTIME_CLI_BIN": str(runtime)}, repo_root=tmp_path)

    assert data["lobster_mode"] == "subcommand"
    assert data["lobster_path"] == str(runtime)
