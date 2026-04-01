"""Unit tests for deterministic predictive preloading in llm_core."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.llm_core.engine_registry import EngineID, TaskDomain
from src.llm_core.predictive_preload import (
    MAX_HISTORY_SIZE,
    COLD_START_CONFIDENCE,
    RECENCY_WINDOW_SECONDS,
    PredictivePreloader,
    PreloadPrediction,
    RequestRecord,
)


class TestPredictivePreloader:
    """Validate recency-frequency-domain forecasting and explicit preload planning."""

    @pytest.fixture
    def preloader(self) -> PredictivePreloader:
        return PredictivePreloader()

    def test_record_single_request(self, preloader: PredictivePreloader):
        """Single request should be retained in bounded history."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        assert len(preloader.history) == 1

    def test_record_multiple_requests(self, preloader: PredictivePreloader):
        """Multiple requests should preserve insertion order."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.REASONING, EngineID.GROK)
        preloader.record_request(TaskDomain.PLANNING, EngineID.MISTRAL)
        history = list(preloader.history.values())
        assert len(history) == 3
        assert history[0].engine_id == EngineID.PHI3
        assert history[1].engine_id == EngineID.GROK
        assert history[2].engine_id == EngineID.MISTRAL

    def test_cold_start_prediction(self, preloader: PredictivePreloader):
        """Cold start should still return ranked engines with bounded confidence."""
        prediction = preloader.predict_next_engines()
        assert isinstance(prediction, PreloadPrediction)
        assert len(prediction.predicted_engines) > 0
        assert prediction.confidence == COLD_START_CONFIDENCE
        assert "Cold start" in prediction.reasoning

    def test_repeated_domain_pattern(self, preloader: PredictivePreloader):
        """Repeated tactical usage should strongly favor Phi-3."""
        for _ in range(3):
            preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        prediction = preloader.predict_next_engines()
        assert prediction.predicted_engines[0] == EngineID.PHI3
        assert prediction.confidence > 0.6

    def test_domain_hint_overrides_history(self, preloader: PredictivePreloader):
        """Domain hint should steer prediction toward domain specialist."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        prediction = preloader.predict_next_engines(domain_hint=TaskDomain.REASONING)
        assert prediction.domain_hint == TaskDomain.REASONING
        assert EngineID.GROK in prediction.predicted_engines

    def test_recency_decay(self, preloader: PredictivePreloader):
        """Recent engine activity should outrank stale historical use."""
        old_record = RequestRecord(
            timestamp=datetime.utcnow() - timedelta(seconds=RECENCY_WINDOW_SECONDS + 60),
            domain=TaskDomain.TACTICAL,
            engine_id=EngineID.PHI3,
            success=True,
            latency_ms=10.0,
        )
        preloader.history["000000"] = old_record
        preloader._history_counter = 1
        for _ in range(3):
            preloader.record_request(TaskDomain.PLANNING, EngineID.MISTRAL)
        prediction = preloader.predict_next_engines()
        assert prediction.predicted_engines[0] == EngineID.MISTRAL

    def test_frequency_score(self, preloader: PredictivePreloader):
        """Higher usage frequency should raise final rank."""
        for _ in range(5):
            preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.REASONING, EngineID.GROK)
        prediction = preloader.predict_next_engines(limit=2)
        assert prediction.predicted_engines[0] == EngineID.PHI3

    def test_alternating_domain_pattern(self, preloader: PredictivePreloader):
        """Alternating tactical/reasoning should keep both engines near top."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.REASONING, EngineID.GROK)
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.REASONING, EngineID.GROK)
        prediction = preloader.predict_next_engines(limit=2)
        assert EngineID.PHI3 in prediction.predicted_engines[:2]
        assert EngineID.GROK in prediction.predicted_engines[:2]

    def test_preload_plan_generation(self, preloader: PredictivePreloader):
        """Preload plan should include always and opportunistic partitions."""
        for _ in range(3):
            preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        prediction = preloader.predict_next_engines(limit=3)
        plan = preloader.build_preload_plan(prediction, always_load_count=1)
        assert len(plan.always_preload) == 1
        assert len(plan.engine_order) == len(prediction.predicted_engines)
        assert plan.estimated_time_ms > 0
        assert plan.memory_required_gb > 0

    def test_preload_plan_memory_budget(self, preloader: PredictivePreloader):
        """Memory budget should trim opportunistic preloads first."""
        preloader.record_request(TaskDomain.PLANNING, EngineID.MISTRAL)
        prediction = preloader.predict_next_engines(limit=3)
        plan = preloader.build_preload_plan(
            prediction=prediction,
            available_memory_gb=3.0,
            always_load_count=1,
        )
        assert len(plan.always_preload) == 1
        assert plan.memory_required_gb <= 6.0

    def test_history_limit(self, preloader: PredictivePreloader):
        """History should never exceed MAX_HISTORY_SIZE entries."""
        all_engines = list(EngineID)
        for i in range(MAX_HISTORY_SIZE * 2):
            preloader.record_request(TaskDomain.TACTICAL, all_engines[i % len(all_engines)])
        assert len(preloader.history) <= MAX_HISTORY_SIZE

    def test_stats_calculation(self, preloader: PredictivePreloader):
        """Stats should report engine and domain cardinality correctly."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.PLANNING, EngineID.MISTRAL)
        stats = preloader.get_stats()
        assert stats["total_requests"] == 2
        assert len(stats["engines_used"]) == 2
        assert len(stats["domains_used"]) == 2
        assert stats["most_common_domain"] in {TaskDomain.TACTICAL.value, TaskDomain.PLANNING.value}

    def test_manual_prediction_only(self, preloader: PredictivePreloader):
        """Prediction API should return artifacts without loading side effects."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        prediction = preloader.predict_next_engines()
        recommendation = prediction.recommendation.lower()
        assert prediction is not None
        assert "preload" in recommendation or "defer" in recommendation

    def test_get_history(self, preloader: PredictivePreloader):
        """History export should preserve domain labels."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.record_request(TaskDomain.REASONING, EngineID.GROK)
        history = preloader.get_history(limit=10)
        assert len(history) == 2
        assert history[0]["domain"] == "tactical"
        assert history[1]["domain"] == "reasoning"

    def test_clear_history(self, preloader: PredictivePreloader):
        """Clear should remove all records."""
        preloader.record_request(TaskDomain.TACTICAL, EngineID.PHI3)
        preloader.clear_history()
        assert len(preloader.history) == 0

    def test_request_record_age_seconds(self):
        """RequestRecord age helper should return non-negative values."""
        now = datetime.utcnow()
        record = RequestRecord(
            timestamp=now - timedelta(seconds=12),
            domain=TaskDomain.TACTICAL,
            engine_id=EngineID.PHI3,
            success=True,
            latency_ms=5.0,
        )
        age = record.age_seconds(current_time=now)
        assert 11.9 <= age <= 12.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
