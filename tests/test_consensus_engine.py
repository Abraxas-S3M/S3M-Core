"""Tests for S3M consensus synchronization engine."""

import pytest

from src.llm_core.consensus_engine import (
    AgreementLevel,
    ConsensusEngine,
    ConsensusMode,
    EngineResponse,
)


class TestConsensusEngine:
    """Test consensus synchronization of 4 engines."""

    @pytest.fixture
    def engine(self):
        return ConsensusEngine(
            disagreement_threshold=0.35,
            confidence_threshold=0.60,
            auto_mode_selection=True,
        )

    def test_full_agreement(self, engine):
        """All engines agree -> ACCEPT, high agreement score."""
        responses = [
            EngineResponse("phi3", "Recommend action X", 150, 100, 0.95, False),
            EngineResponse("grok", "Recommend action X", 140, 100, 0.92, False),
            EngineResponse("mistral", "Recommend action X", 160, 100, 0.88, False),
            EngineResponse("allam", "Recommend action X", 145, 100, 0.85, False),
        ]

        result = engine.synthesize(responses)

        assert result.review_status == "ACCEPT"
        assert result.agreement_score >= 0.80
        assert result.disagreement_score <= 0.20
        assert "action x" in result.final_text.lower()

    def test_partial_disagreement(self, engine):
        """Mixed responses -> REVIEW, moderate agreement."""
        responses = [
            EngineResponse("phi3", "Recommend action X", 150, 100, 0.92, False),
            EngineResponse("grok", "Recommend action X", 140, 100, 0.88, False),
            EngineResponse("mistral", "Recommend action Y", 160, 100, 0.75, False),
            EngineResponse("allam", "Recommend action Z", 145, 100, 0.70, False),
        ]

        result = engine.synthesize(responses)

        assert result.review_status == "REVIEW"
        assert 0.4 < result.agreement_score < 0.7
        assert result.disagreement_score > 0.25
        assert result.agreement_level in {
            AgreementLevel.WEAK_AGREEMENT.value,
            AgreementLevel.MODERATE_AGREEMENT.value,
        }

    def test_one_engine_failure(self, engine):
        """One engine fails -> use remaining engines."""
        responses = [
            EngineResponse("phi3", "Recommend action X", 150, 100, 0.95, False),
            EngineResponse("grok", "Recommend action X", 140, 100, 0.92, False),
            EngineResponse("mistral", "Recommend action X", 160, 100, 0.88, False),
            EngineResponse("allam", "Failed response", 0, 0, 0.0, True, "Out of memory"),
        ]

        result = engine.synthesize(responses)

        assert len(result.engines_used) == 3
        assert "allam" in result.engines_failed
        assert result.review_status == "ACCEPT"
        assert "action x" in result.final_text.lower()

    def test_all_engines_failed(self, engine):
        """All engines fail -> REJECT with error details."""
        responses = [
            EngineResponse("phi3", "Error", 0, 0, 0.0, True, "OOM"),
            EngineResponse("grok", "Error", 0, 0, 0.0, True, "Timeout"),
            EngineResponse("mistral", "Error", 0, 0, 0.0, True, "OOM"),
            EngineResponse("allam", "Error", 0, 0, 0.0, True, "Network"),
        ]

        result = engine.synthesize(responses)

        assert result.review_status == "REJECT"
        assert len(result.engines_failed) == 4
        assert "[ERROR]" in result.final_text

    def test_low_confidence_triggers_review(self, engine):
        """Any engine below confidence threshold triggers REVIEW."""
        responses = [
            EngineResponse("phi3", "Recommend action X", 150, 100, 0.95, False),
            EngineResponse("grok", "Recommend action X", 140, 100, 0.88, False),
            EngineResponse("mistral", "Recommend action X", 160, 100, 0.50, False),
            EngineResponse("allam", "Recommend action X", 145, 100, 0.85, False),
        ]

        result = engine.synthesize(responses)

        assert result.review_status == "REVIEW"
        assert result.confidence_threshold_met is False
        assert result.winning_strategy == ConsensusMode.ABSTAIN_ON_LOW_CONFIDENCE.value
        assert result.final_text.startswith("[LOW CONFIDENCE]")

    def test_empty_responses(self, engine):
        """No responses provided -> REJECT error."""
        result = engine.synthesize([])

        assert result.review_status == "REJECT"
        assert "[ERROR]" in result.final_text
        assert result.agreement_score == 0.0

    def test_majority_vote_mode(self, engine):
        """Explicit MAJORITY_VOTE mode."""
        responses = [
            EngineResponse("phi3", "Action X", 150, 100, 0.95, False),
            EngineResponse("grok", "Action X", 140, 100, 0.92, False),
            EngineResponse("mistral", "Action Y", 160, 100, 0.75, False),
            EngineResponse("allam", "Action Z", 145, 100, 0.70, False),
        ]

        result = engine.synthesize(responses, mode=ConsensusMode.MAJORITY_VOTE)

        assert result.winning_strategy == "majority_vote"
        assert "Action X" in result.final_text

    def test_hierarchical_mode(self, engine):
        """Explicit HIERARCHICAL mode -> highest confidence engine."""
        responses = [
            EngineResponse("phi3", "Action X", 150, 100, 0.80, False),
            EngineResponse("grok", "Action Y", 140, 100, 0.95, False),
            EngineResponse("mistral", "Action Z", 160, 100, 0.75, False),
            EngineResponse("allam", "Action A", 145, 100, 0.70, False),
        ]

        result = engine.synthesize(responses, mode=ConsensusMode.HIERARCHICAL_RESOLUTION)

        assert result.winning_strategy == "hierarchical_resolution"
        assert "Action Y" in result.final_text

    def test_weights_are_normalized(self, engine):
        """Engine weights must sum to 1.0 for deterministic arbitration."""
        responses = [
            EngineResponse("phi3", "Action X", 150, 100, 0.8, False),
            EngineResponse("grok", "Action X", 140, 100, 0.7, False),
            EngineResponse("mistral", "Action X", 160, 100, 0.6, False),
            EngineResponse("allam", "Action X", 145, 100, 0.9, False),
        ]

        result = engine.synthesize(responses)
        total = sum(result.per_engine_weights.values())
        assert total == pytest.approx(1.0, rel=1e-6, abs=1e-6)

    def test_result_to_dict_schema(self, engine):
        """Result payload includes all expected keys for API serialization."""
        responses = [
            EngineResponse("phi3", "Action X", 150, 100, 0.9, False),
            EngineResponse("grok", "Action X", 140, 100, 0.9, False),
        ]
        result = engine.synthesize(responses)
        payload = result.to_dict()

        expected_keys = {
            "final_text",
            "agreement_score",
            "disagreement_score",
            "winning_strategy",
            "per_engine_weights",
            "per_engine_scores",
            "review_status",
            "agreement_level",
            "voting_matrix",
            "engines_used",
            "engines_failed",
            "confidence_threshold_met",
        }
        assert expected_keys.issubset(payload.keys())

