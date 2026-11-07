"""Planning gate aggregation tests."""

from __future__ import annotations

from src.integrations.lechonk.planning_gates import evaluate_planning_gates

REPO_ENGINES = "configs/engines.yaml"


def test_gates_closed_by_default() -> None:
    gates = evaluate_planning_gates(engines_path=REPO_ENGINES)
    assert gates.may_use_lechonk is False
    assert gates.reasons
