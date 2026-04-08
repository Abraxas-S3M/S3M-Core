"""
Comprehensive tests for Confidence Framework and orchestrator integration.
"""

import sys

import pytest

sys.path.insert(0, ".")

from src.llm_core.advanced_orchestrator import AdvancedOrchestrator
from src.llm_core.confidence_framework import (
    ACCEPT_THRESHOLD,
    REVIEW_THRESHOLD,
    ConfidenceFactors,
    ConfidenceFramework,
    ConfidenceInput,
    ReviewStatus,
)
from src.llm_core.engine_registry import TaskDomain


class TestConfidenceFrameworkCore:
    """Core confidence scoring tests."""

    @pytest.fixture
    def framework(self):
        return ConfidenceFramework()

    @pytest.fixture
    def baseline_inputs(self):
        return {
            "response_text": (
                "The answer is 42 based on the following reasoning. "
                "This is a complete response."
            ),
            "routing_certainty": 0.85,
            "engine_health": {"phi3-medium": "HEALTHY", "grok1-314b": "HEALTHY"},
            "engine_responses": {
                "phi3-medium": "42 based reasoning",
                "grok1-314b": "42 based reasoning",
            },
            "selected_engines": ["phi3-medium", "grok1-314b"],
            "failover_used": False,
            "model_drift_detected": False,
        }

    def test_high_confidence_accept(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        assert score.confidence_score >= ACCEPT_THRESHOLD
        assert score.review_status == ReviewStatus.ACCEPT.value
        assert len(score.reasoning) >= 6
        assert not score.penalties_applied

    def test_medium_confidence_review(self, framework, baseline_inputs):
        inputs = dict(baseline_inputs)
        inputs["routing_certainty"] = 0.70
        inputs["engine_health"] = {"phi3-medium": "HEALTHY", "grok1-314b": "DEGRADED"}
        inputs["engine_responses"] = {"phi3-medium": "Answer A", "grok1-314b": "Answer B"}
        score = framework.score_decision(**inputs)
        assert REVIEW_THRESHOLD <= score.confidence_score < ACCEPT_THRESHOLD
        assert score.review_status == ReviewStatus.REVIEW.value

    def test_low_confidence_reject(self, framework, baseline_inputs):
        inputs = dict(baseline_inputs)
        inputs["routing_certainty"] = 0.40
        inputs["engine_health"] = {"phi3-medium": "DEGRADED", "grok1-314b": "UNAVAILABLE"}
        inputs["engine_responses"] = {"phi3-medium": "unclear", "grok1-314b": ""}
        inputs["failover_used"] = True
        inputs["model_drift_detected"] = True
        score = framework.score_decision(**inputs)
        assert score.confidence_score < REVIEW_THRESHOLD
        assert score.review_status == ReviewStatus.REJECT.value
        assert len(score.penalties_applied) > 0

    def test_empty_response_always_reject(self, framework, baseline_inputs):
        inputs = dict(baseline_inputs)
        inputs["response_text"] = ""
        score = framework.score_decision(**inputs)
        assert score.review_status == ReviewStatus.REJECT.value
        assert any("empty response" in line.lower() for line in score.reasoning)

    def test_failover_penalty(self, framework, baseline_inputs):
        score_no_failover = framework.score_decision(**baseline_inputs)
        inputs_failover = dict(baseline_inputs)
        inputs_failover["failover_used"] = True
        score_with_failover = framework.score_decision(**inputs_failover)
        assert score_no_failover.confidence_score > score_with_failover.confidence_score
        assert any("failover" in penalty.lower() for penalty in score_with_failover.penalties_applied)

    def test_model_drift_penalty(self, framework, baseline_inputs):
        score_no_drift = framework.score_decision(**baseline_inputs)
        inputs_drift = dict(baseline_inputs)
        inputs_drift["model_drift_detected"] = True
        score_with_drift = framework.score_decision(**inputs_drift)
        assert score_no_drift.confidence_score > score_with_drift.confidence_score
        assert any("drift" in penalty.lower() for penalty in score_with_drift.penalties_applied)

    def test_low_health_penalty(self, framework, baseline_inputs):
        inputs = dict(baseline_inputs)
        inputs["engine_health"] = {"phi3-medium": "UNAVAILABLE", "grok1-314b": "DEGRADED"}
        score = framework.score_decision(**inputs)
        assert score.factors.engine_health < 0.7
        assert any("health" in penalty.lower() for penalty in score.penalties_applied)

    def test_disagreement_penalty(self, framework, baseline_inputs):
        inputs = dict(baseline_inputs)
        inputs["engine_responses"] = {
            "phi3-medium": "Answer is definitely A for these reasons",
            "grok1-314b": "Answer is definitely B for different reasons",
        }
        score = framework.score_decision(**inputs)
        if score.factors.agreement_strength < 0.6:
            assert any("agreement" in penalty.lower() for penalty in score.penalties_applied)

    def test_reasoning_transparency(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        reasoning_text = " ".join(score.reasoning).lower()
        assert "routing" in reasoning_text
        assert "health" in reasoning_text
        assert "agreement" in reasoning_text
        assert "completeness" in reasoning_text
        assert "failover" in reasoning_text
        assert "verification" in reasoning_text

    def test_factors_valid_range(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        for name, value in score.factors.to_dict().items():
            assert 0.0 <= value <= 1.0, f"{name} out of range: {value}"

    def test_score_in_valid_range(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        assert 0.0 <= score.confidence_score <= 1.0

    def test_audit_id_generated(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        assert score.audit_id

    def test_multiple_engines_agreement(self, framework):
        score = framework.score_decision(
            response_text="The answer is 42.",
            routing_certainty=0.85,
            engine_health={
                "phi3-medium": "HEALTHY",
                "grok1-314b": "HEALTHY",
                "mixtral-8x7b": "HEALTHY",
            },
            engine_responses={
                "phi3-medium": "The answer is 42.",
                "grok1-314b": "The answer is 42.",
                "mixtral-8x7b": "The answer is 42.",
            },
            selected_engines=["phi3-medium", "grok1-314b", "mixtral-8x7b"],
        )
        assert score.factors.agreement_strength > 0.85

    def test_health_averaging(self, framework):
        score = framework.score_decision(
            response_text="Good response.",
            routing_certainty=0.85,
            engine_health={"phi3-medium": "HEALTHY", "grok1-314b": "DEGRADED"},
            engine_responses={"phi3-medium": "response", "grok1-314b": "response"},
            selected_engines=["phi3-medium", "grok1-314b"],
        )
        assert 0.7 <= score.factors.engine_health <= 1.0

    def test_completeness_scoring(self, framework):
        score_short = framework.score_decision(
            response_text="Yes.",
            routing_certainty=0.85,
            engine_health={"phi3-medium": "HEALTHY"},
            engine_responses={"phi3-medium": "Yes."},
            selected_engines=["phi3-medium"],
        )
        score_long = framework.score_decision(
            response_text=(
                "The answer is 42 because of detailed reasoning. "
                "Multiple factors contribute. This is well-explained."
            ),
            routing_certainty=0.85,
            engine_health={"phi3-medium": "HEALTHY"},
            engine_responses={"phi3-medium": "detailed response"},
            selected_engines=["phi3-medium"],
        )
        assert (
            score_long.factors.response_completeness
            > score_short.factors.response_completeness
        )

    def test_to_dict_serialization(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        payload = score.to_dict()
        assert isinstance(payload, dict)
        assert "confidence_score" in payload
        assert "review_status" in payload
        assert "factors" in payload
        assert "reasoning" in payload

    def test_summary_generation(self, framework, baseline_inputs):
        score = framework.score_decision(**baseline_inputs)
        summary = score.summary()
        assert "CONFIDENCE ASSESSMENT SUMMARY" in summary
        assert score.review_status in summary

    def test_history_read_and_clear(self, framework, baseline_inputs):
        framework.score_decision(**baseline_inputs)
        framework.score_decision(**baseline_inputs)
        history = framework.get_scoring_history(limit=1)
        assert len(history) == 1
        framework.clear_history()
        assert framework.get_scoring_history() == []

    def test_confidence_factors_validation(self):
        with pytest.raises(ValueError):
            ConfidenceFactors(
                routing_certainty=1.1,
                engine_health=1.0,
                agreement_strength=1.0,
                response_completeness=1.0,
                failover_penalty=1.0,
                model_verification=1.0,
            )


class TestConfidenceInputValidation:
    """Input validation tests."""

    def test_invalid_routing_certainty(self):
        input_obj = ConfidenceInput(
            response_text="response",
            routing_certainty=1.5,
            engine_health={"phi3-medium": "HEALTHY"},
            engine_responses={"phi3-medium": "response"},
            selected_engines=["phi3-medium"],
            failover_used=False,
            model_drift_detected=False,
        )
        is_valid, error = input_obj.validate()
        assert not is_valid
        assert "routing_certainty" in str(error)

    def test_unknown_health_state(self):
        input_obj = ConfidenceInput(
            response_text="response",
            routing_certainty=0.85,
            engine_health={"phi3-medium": "INVALID"},
            engine_responses={"phi3-medium": "response"},
            selected_engines=["phi3-medium"],
            failover_used=False,
            model_drift_detected=False,
        )
        is_valid, _ = input_obj.validate()
        assert not is_valid

    def test_missing_selected_engines(self):
        input_obj = ConfidenceInput(
            response_text="response",
            routing_certainty=0.85,
            engine_health={"phi3-medium": "HEALTHY"},
            engine_responses={"phi3-medium": "response"},
            selected_engines=[],
            failover_used=False,
            model_drift_detected=False,
        )
        is_valid, error = input_obj.validate()
        assert not is_valid
        assert "selected_engines" in str(error)


class TestOrchestratorConfidenceIntegration:
    """Integration tests for execute_with_confidence."""

    def test_execute_with_confidence_shape(self):
        orchestrator = AdvancedOrchestrator()
        result = orchestrator.execute_with_confidence(
            prompt="analyze and evaluate implications of force posture",
            domain=TaskDomain.REASONING,
        )
        assert "response" in result
        assert "confidence_score" in result
        assert "review_status" in result
        assert "confidence_factors" in result
        assert "confidence_summary" in result
        assert "audit_id" in result

    def test_execute_with_confidence_ranges(self):
        orchestrator = AdvancedOrchestrator()
        result = orchestrator.execute_with_confidence(prompt="status update")
        assert 0.0 <= result["confidence_score"] <= 1.0
        assert result["review_status"] in {
            ReviewStatus.ACCEPT.value,
            ReviewStatus.REVIEW.value,
            ReviewStatus.REJECT.value,
        }
        factors = result["confidence_factors"]
        assert set(factors.keys()) == {
            "routing_certainty",
            "engine_health",
            "agreement_strength",
            "response_completeness",
            "failover_penalty",
            "model_verification",
        }

    def test_execute_with_confidence_summary_text(self):
        orchestrator = AdvancedOrchestrator()
        result = orchestrator.execute_with_confidence(prompt="enemy position at grid 123")
        assert "CONFIDENCE ASSESSMENT SUMMARY" in result["confidence_summary"]
        assert result["review_status"] in result["confidence_summary"]

