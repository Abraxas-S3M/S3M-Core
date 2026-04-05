"""Unit tests for unified cognitive engine integration behavior."""

from __future__ import annotations

from dataclasses import dataclass

from src.cognitive import UnifiedCognitiveEngine


@dataclass
class _Option:
    label: str
    probability_of_success: float


class _BackendOk:
    def evaluate(self, options, belief_state=None, author_id=None):  # noqa: ANN001
        selected = type(
            "Selected",
            (),
            {
                "option": _Option(label="backend", probability_of_success=0.99),
                "utility_score": 0.95,
            },
        )()
        result = type(
            "Result",
            (),
            {
                "selected": selected,
                "confidence": 0.9,
                "requires_human_review": False,
            },
        )()
        return type("DecisionResult", (), {"result": result})()


class _BackendFail:
    def evaluate(self, options, belief_state=None, author_id=None):  # noqa: ANN001
        raise RuntimeError("backend unavailable")


def test_unified_engine_fallback_selects_highest_scored_option() -> None:
    engine = UnifiedCognitiveEngine(min_decision_confidence=0.4)
    options = [
        {"label": "low", "probability_of_success": 0.3, "confidence": 0.2, "utility_score": 0.3},
        {"label": "high", "probability_of_success": 0.8, "confidence": 0.6, "utility_score": 0.7},
    ]

    decision = engine.evaluate(options=options, belief_state=None, author_id="tester")

    assert decision is not None
    assert decision.backend == "deterministic_fallback"
    assert decision.result.selected.option.label == "high"
    assert decision.result.confidence >= 0.4
    assert decision.result.requires_human_review is False


def test_unified_engine_returns_backend_decision_when_valid() -> None:
    backend = _BackendOk()
    engine = UnifiedCognitiveEngine(decision_engine=backend)
    options = [_Option(label="a", probability_of_success=0.1)]

    decision = engine.evaluate(options=options, belief_state=None, author_id="tester")

    assert decision is not None
    assert decision.result.selected.option.label == "backend"
    assert decision.result.confidence == 0.9


def test_unified_engine_falls_back_when_backend_faults() -> None:
    engine = UnifiedCognitiveEngine(decision_engine=_BackendFail(), min_decision_confidence=0.8)
    options = [_Option(label="fallback", probability_of_success=0.5)]

    decision = engine.evaluate(options=options, belief_state=None, author_id="tester")

    assert decision is not None
    assert decision.backend == "deterministic_fallback"
    assert decision.result.selected.option.label == "fallback"
