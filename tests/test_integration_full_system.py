"""
Integration tests for complete Quad-Engine orchestration.
Tests orchestrator + failover + confidence + preload + registry + monitor.
"""

from __future__ import annotations

import pytest

from src.dashboard.providers.llm_monitor_provider import LLMMonitorProvider
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator


class TestFullSystemIntegration:
    """Validate backward compatibility and v2 integration surfaces."""

    @pytest.fixture
    def orchestrator(self) -> Orchestrator:
        return Orchestrator()

    @pytest.fixture
    def monitor(self, orchestrator: Orchestrator) -> LLMMonitorProvider:
        return LLMMonitorProvider(orchestrator)

    def test_legacy_api_backward_compatible(self, orchestrator: Orchestrator) -> None:
        result = orchestrator.route_and_decide(prompt="What is the capital of France?")
        assert "recommendation_text" in result
        assert "strategy" in result
        assert "selected_engines" in result
        assert "audit_id" in result

    def test_advanced_api_confidence(self, orchestrator: Orchestrator) -> None:
        result = orchestrator.execute_with_confidence(prompt="What is the capital of France?")
        assert "confidence_score" in result
        assert "review_status" in result
        assert "confidence_factors" in result
        assert "confidence_reasoning" in result
        assert 0.0 <= result["confidence_score"] <= 1.0

    def test_failover_awareness(self, orchestrator: Orchestrator) -> None:
        result = orchestrator.route_with_failover(prompt="Question?")
        assert "failover_used" in result
        assert "healthy_engines" in result
        assert "unavailable_engines" in result

    def test_preload_prediction(self, orchestrator: Orchestrator) -> None:
        result = orchestrator.predict_next_engines()
        assert "predicted_engines" in result
        assert "confidence" in result
        assert "reasoning" in result

    def test_system_health_check(self, orchestrator: Orchestrator) -> None:
        health = orchestrator.check_system_health()
        assert "overall_status" in health
        assert "models" in health
        assert "engines" in health
        assert "issues" in health
        assert health["overall_status"] in ["HEALTHY", "DEGRADED"]

    def test_system_recommendations(self, orchestrator: Orchestrator) -> None:
        recs = orchestrator.get_system_recommendations()
        assert "resource_allocation" in recs
        assert "preload_suggestion" in recs
        assert "maintenance_alerts" in recs

    def test_domain_hint_prediction(self, orchestrator: Orchestrator) -> None:
        pred = orchestrator.predict_next_engines(domain_hint=TaskDomain.REASONING, limit=2)
        assert isinstance(pred["predicted_engines"], list)
        assert len(pred["predicted_engines"]) >= 1

    def test_monitor_orchestrator_status(self, monitor: LLMMonitorProvider) -> None:
        status = monitor.get_orchestrator_status()
        assert "overall_status" in status
        assert "models" in status
        assert "engines" in status

    def test_monitor_routing_intelligence(self, monitor: LLMMonitorProvider) -> None:
        intel = monitor.get_routing_intelligence()
        assert "recent_decisions" in intel
        assert "strategy_distribution" in intel
        assert "avg_latency_ms" in intel

    def test_monitor_engine_health(self, monitor: LLMMonitorProvider) -> None:
        health = monitor.get_engine_health_dashboard()
        assert isinstance(health, dict)
        for _, state in health.items():
            assert "state" in state
            assert "success_rate" in state

    def test_monitor_confidence_analytics(self, monitor: LLMMonitorProvider) -> None:
        # Seed one confidence entry so analytics can compute non-empty sets.
        monitor.orchestrator.execute_with_confidence(prompt="status check")
        confidence = monitor.get_confidence_dashboard()
        assert "avg_confidence" in confidence
        assert "accept_rate" in confidence
        assert "review_rate" in confidence
        assert "reject_rate" in confidence

    def test_monitor_failover_status(self, monitor: LLMMonitorProvider) -> None:
        failover = monitor.get_failover_status()
        assert "active" in failover
        assert "total_activations" in failover
        assert "recent_activations" in failover

    def test_monitor_model_verification(self, monitor: LLMMonitorProvider) -> None:
        models = monitor.get_model_verification_status()
        assert "clean_artifacts" in models
        assert "missing_artifacts" in models
        assert "artifacts" in models

    def test_monitor_preload_intelligence(self, monitor: LLMMonitorProvider) -> None:
        preload = monitor.get_preload_intelligence()
        assert "total_requests_tracked" in preload
        assert "recent_history" in preload

    def test_monitor_full_dashboard(self, monitor: LLMMonitorProvider) -> None:
        dashboard = monitor.get_full_system_dashboard()
        assert "orchestrator" in dashboard
        assert "routing" in dashboard
        assert "engines" in dashboard
        assert "confidence" in dashboard
        assert "failover" in dashboard
        assert "models" in dashboard
        assert "preload" in dashboard

    def test_monitor_alerts(self, monitor: LLMMonitorProvider) -> None:
        alerts = monitor.get_alerts()
        assert isinstance(alerts, list)
        for alert in alerts:
            assert "severity" in alert
            assert "type" in alert
            assert "message" in alert

