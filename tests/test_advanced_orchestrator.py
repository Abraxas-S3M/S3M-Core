"""Advanced orchestrator tests for adaptive routing and compatibility."""

import sys

sys.path.insert(0, ".")

from src.llm_core.advanced_orchestrator import (
    AdvancedOrchestrator,
    RoutingStrategy,
    UrgencyLevel,
)
from src.llm_core.engine_registry import EngineID, TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


def test_tactical_classification():
    orch = AdvancedOrchestrator()
    domain = orch._classify_domain("enemy position at grid 123 with patrol movement")
    assert domain == TaskDomain.TACTICAL


def test_reasoning_classification():
    orch = AdvancedOrchestrator()
    domain = orch._classify_domain("analyze and evaluate implications of force posture")
    assert domain == TaskDomain.REASONING


def test_critical_urgency_triggers_consensus():
    orch = AdvancedOrchestrator()
    request = QueryRequest(prompt="critical urgent threat assessment now")
    response = orch.route_and_decide(request)
    assert response.normalized_strategy == RoutingStrategy.CONSENSUS
    assert len(response.engine_trace) == 4


def test_time_constraint_selects_fast():
    orch = AdvancedOrchestrator()
    request = QueryRequest(prompt="status update", max_latency_ms=250.0)
    response = orch.route_and_decide(request)
    assert response.normalized_strategy == RoutingStrategy.SINGLE_ENGINE
    assert response.engine_trace == [EngineID.PHI3_MEDIUM]


def test_arabic_routing():
    orch = AdvancedOrchestrator()
    request = QueryRequest(prompt="ما هي خطة التحرك في القطاع")
    response = orch.route_and_decide(request)
    assert response.normalized_strategy == RoutingStrategy.SINGLE_ENGINE
    assert response.engine_trace == [EngineID.ALLAM]


def test_engine_weights_normalized():
    orch = AdvancedOrchestrator()
    weights = orch._calculate_engine_weights(
        prompt="analyze threat and evaluate movement",
        domain=TaskDomain.REASONING,
        urgency=UrgencyLevel.HIGH,
        max_latency_ms=None,
    )
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert set(weights.keys()) == set(EngineID)


def test_backward_compatibility():
    orch = Orchestrator()

    # Legacy behavior remains unchanged.
    legacy = orch.process(QueryRequest(prompt="enemy position grid 7"))
    assert legacy.engine_id == EngineID.PHI3_MEDIUM

    # Advanced path provides richer routing envelope.
    advanced = orch.route_advanced(QueryRequest(prompt="analyze implications of supply route"))
    assert hasattr(advanced, "audit_id")
    assert hasattr(advanced, "confidence_score")
