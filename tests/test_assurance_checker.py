"""Tests for autonomy assurance checker policy gates."""

from __future__ import annotations

from datetime import datetime, timezone

from src.autonomy.models import AutonomyDecision, DecisionType
from src.autonomy.xai import AssuranceChecker


def _decision(
    decision_id: str,
    decision_type: DecisionType,
    confidence: float = 0.8,
    risk_score: float = 0.2,
    context: dict | None = None,
) -> AutonomyDecision:
    return AutonomyDecision(
        decision_id=decision_id,
        timestamp=datetime.now(timezone.utc),
        decision_type=decision_type,
        agent_id="a1",
        mission_id="m1",
        context=context or {},
        action_taken={"action": decision_type.value},
        alternatives_considered=[],
        confidence=confidence,
        reasoning="tactical reason",
        llm_consulted=False,
        requires_human_review=False,
        risk_score=risk_score,
    )


def test_high_risk_requires_review():
    checker = AssuranceChecker(risk_threshold=0.7)
    d = _decision("d1", DecisionType.HOLD, risk_score=0.9)
    result = checker.check(d)
    assert result["requires_human_review"] is True


def test_low_confidence_requires_review():
    checker = AssuranceChecker(confidence_threshold=0.3)
    d = _decision("d2", DecisionType.HOLD, confidence=0.2)
    result = checker.check(d)
    assert result["requires_human_review"] is True


def test_engage_under_weapons_hold_blocked():
    checker = AssuranceChecker()
    d = _decision("d3", DecisionType.ENGAGE, context={"rules_of_engagement": "weapons_hold"})
    result = checker.check(d)
    assert result["approved"] is False
    assert "roe_violation_weapons_hold" in result["flags"]


def test_strike_always_requires_review():
    checker = AssuranceChecker()
    d = _decision("d4", DecisionType.STRIKE)
    result = checker.check(d)
    assert result["requires_human_review"] is True


def test_normal_decision_approved():
    checker = AssuranceChecker()
    d = _decision("d5", DecisionType.HOLD, confidence=0.9, risk_score=0.1)
    result = checker.check(d)
    assert result["approved"] is True
    assert result["requires_human_review"] is False
