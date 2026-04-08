"""Tests for military-grade failover system behavior."""

from datetime import datetime, timedelta

import pytest

from src.llm_core.engine_registry import EngineID, TaskDomain
from src.llm_core.failover_system import (
    FailoverMode,
    FailoverSystem,
    HealthState,
)


class TestFailoverSystem:
    """Validate failover state machine, fallback, and audit safeguards."""

    @pytest.fixture
    def failover(self) -> FailoverSystem:
        return FailoverSystem()

    def test_initial_state(self, failover: FailoverSystem) -> None:
        """All engines must start healthy and routable."""
        for engine_id in EngineID:
            assert failover.health[engine_id].state == HealthState.HEALTHY
        healthy = failover.get_healthy_engines()
        assert set(healthy) == set(EngineID)

    def test_single_failure_degrades(self, failover: FailoverSystem) -> None:
        """First failure should move engine to degraded posture."""
        failover.mark_failure(EngineID.PHI3_MEDIUM, "timeout")
        assert failover.health[EngineID.PHI3_MEDIUM].state == HealthState.DEGRADED

    def test_multiple_failures_trip_circuit(self, failover: FailoverSystem) -> None:
        """Three close failures must trip circuit above weighted threshold."""
        for i in range(3):
            failover.mark_failure(EngineID.GROK1, f"failure_{i}")
        assert failover.health[EngineID.GROK1].state == HealthState.UNAVAILABLE
        assert failover.should_trip_circuit(EngineID.GROK1)

    def test_recovery_after_cooldown(self, failover: FailoverSystem) -> None:
        """Unavailable engine transitions through warming and recovers on success."""
        for i in range(3):
            failover.mark_failure(EngineID.MIXTRAL, f"failure_{i}")
        assert failover.health[EngineID.MIXTRAL].state == HealthState.UNAVAILABLE

        failover.health[EngineID.MIXTRAL].circuit_open_time = datetime.utcnow() - timedelta(
            seconds=65
        )
        assert not failover.should_trip_circuit(EngineID.MIXTRAL)
        assert failover.health[EngineID.MIXTRAL].state == HealthState.WARMING

        failover.mark_success(EngineID.MIXTRAL)
        assert failover.health[EngineID.MIXTRAL].state == HealthState.HEALTHY

    def test_healthy_engines_excludes_unavailable(self, failover: FailoverSystem) -> None:
        """Unavailable engine must never be listed as healthy candidate."""
        for _ in range(3):
            failover.mark_failure(EngineID.PHI3_MEDIUM, "down")
        healthy = failover.get_healthy_engines()
        assert EngineID.PHI3_MEDIUM not in healthy
        assert len(healthy) == 3

    def test_failover_mode_full_quad(self, failover: FailoverSystem) -> None:
        """All four engines available means full-quad posture."""
        _, mode = failover.get_available_engines_by_mode()
        assert mode == FailoverMode.FULL_QUAD

    def test_failover_mode_dual_engine(self, failover: FailoverSystem) -> None:
        """Three available engines maps to dual-engine degraded mode."""
        for _ in range(3):
            failover.mark_failure(EngineID.ALLAM, "down")
        _, mode = failover.get_available_engines_by_mode()
        assert mode == FailoverMode.DUAL_ENGINE

    def test_failover_mode_single_tactical(self, failover: FailoverSystem) -> None:
        """One available engine maps to single tactical posture."""
        for engine_id in [EngineID.PHI3_MEDIUM, EngineID.GROK1, EngineID.MIXTRAL]:
            for _ in range(3):
                failover.mark_failure(engine_id, "down")
        _, mode = failover.get_available_engines_by_mode()
        assert mode == FailoverMode.SINGLE_TACTICAL

    def test_failover_mode_deterministic(self, failover: FailoverSystem) -> None:
        """No available engines forces deterministic mode."""
        for engine_id in EngineID:
            for _ in range(3):
                failover.mark_failure(engine_id, "down")
        _, mode = failover.get_available_engines_by_mode()
        assert mode == FailoverMode.DETERMINISTIC

    def test_deterministic_response_requires_review(self, failover: FailoverSystem) -> None:
        """Deterministic response must enforce non-autonomous review posture."""
        response = failover.get_deterministic_response(TaskDomain.TACTICAL, "enemy movement")
        assert response.review_status in {"REVIEW", "REJECT"}
        assert response.confidence_score == 0.0
        assert response.failover_used is True
        assert "action:" in response.safe_template or "الإجراء:" in response.safe_template

    def test_failure_audit_trail_records_events(self, failover: FailoverSystem) -> None:
        """Every failure should be persisted for post-mission forensics."""
        failover.mark_failure(EngineID.PHI3_MEDIUM, "timeout", {"code": "E_TIMEOUT"})
        failover.mark_failure(EngineID.GROK1, "oom", {"code": "E_OOM"})
        records = failover.get_failure_history()
        assert len(records) >= 2
        assert {record["engine_id"] for record in records}.issuperset(
            {EngineID.PHI3_MEDIUM.value, EngineID.GROK1.value}
        )

    def test_weighted_failures_decay_over_time(self, failover: FailoverSystem) -> None:
        """Recent failures must carry more weight than old ones."""
        failover.mark_failure(EngineID.ALLAM, "new")
        recent_weight = failover._get_effective_failure_count(EngineID.ALLAM)
        failover.failure_history[EngineID.ALLAM][0].timestamp = datetime.utcnow() - timedelta(
            seconds=120
        )
        old_weight = failover._get_effective_failure_count(EngineID.ALLAM)
        assert old_weight < recent_weight
        assert old_weight > 0.0

    def test_choose_fallback_prefers_healthy(self, failover: FailoverSystem) -> None:
        """Fallback selection must prioritize healthy engine deterministically."""
        for _ in range(3):
            failover.mark_failure(EngineID.GROK1, "unavailable")
        chosen = failover.choose_fallback(
            primary_engine=EngineID.PHI3_MEDIUM,
            candidate_engines=[EngineID.GROK1, EngineID.MIXTRAL, EngineID.ALLAM],
        )
        assert chosen in {EngineID.MIXTRAL, EngineID.ALLAM}
        assert failover.health[chosen].state in {HealthState.HEALTHY, HealthState.DEGRADED}

    def test_record_failover_appends_audit(self, failover: FailoverSystem) -> None:
        """Failover record should be queryable in audit history."""
        audit_id = failover.record_failover(
            primary=EngineID.PHI3_MEDIUM,
            fallbacks_tried=[EngineID.GROK1, EngineID.MIXTRAL],
            succeeded=EngineID.MIXTRAL,
            reason="primary timeout",
            latency_ms=42.0,
        )
        history = failover.get_failover_history()
        assert history[-1]["audit_id"] == audit_id
        assert history[-1]["succeeded"] == EngineID.MIXTRAL.value

