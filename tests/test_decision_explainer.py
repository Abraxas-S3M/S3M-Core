#!/usr/bin/env python3
"""Tests for autonomy decision explainer."""

from __future__ import annotations

from datetime import datetime, timezone

from src.autonomy.models import AutonomyDecision, DecisionType
from src.autonomy.xai.decision_explainer import DecisionExplainer


def _decision() -> AutonomyDecision:
    return AutonomyDecision(
        decision_id="dec-exp",
        timestamp=datetime.now(timezone.utc),
        decision_type=DecisionType.ENGAGE,
        agent_id="a1",
        mission_id="m1",
        context={"threat_level": 0.8, "rules_of_engagement": "weapons_free"},
        action_taken={"action": "engage"},
        alternatives_considered=[{"option": "retreat", "reason": "objective priority"}],
        confidence=0.8,
        reasoning="Threat was within engagement envelope.",
        llm_consulted=False,
        requires_human_review=False,
        risk_score=0.6,
    )


def test_explain_returns_required_keys() -> None:
    explainer = DecisionExplainer()
    out = explainer.explain(_decision())
    assert "summary" in out
    assert "factors" in out
    assert "risk_assessment" in out


def test_explain_for_operator_is_readable() -> None:
    explainer = DecisionExplainer()
    text = explainer.explain_for_operator(_decision())
    assert "The system chose to" in text
    assert "Confidence:" in text


def test_explain_batch_distribution() -> None:
    explainer = DecisionExplainer()
    out = explainer.explain_batch([_decision(), _decision()])
    assert out["count"] == 2
    assert "confidence_distribution" in out
