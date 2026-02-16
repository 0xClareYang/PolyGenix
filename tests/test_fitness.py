from __future__ import annotations

from tools.evolution.compare import compute_fitness


def test_compute_fitness_basic() -> None:
    summary = {
        "signal_rate": 0.2,
        "http_success_rate": 0.9,
        "error_rate": 0.1,
        "rest_p95_ms": 500,
    }

    score = compute_fitness(summary)
    # score = 2*0.2 + 1.5*0.9 - 1.0*(0.5) - 1.5*0.1
    expected = 0.4 + 1.35 - 0.5 - 0.15
    assert abs(score - expected) < 1e-9


def test_compute_fitness_missing_values() -> None:
    summary = {}
    score = compute_fitness(summary)
    assert score == 0.0
