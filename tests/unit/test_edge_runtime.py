"""Unit tests for S3M Phase 21 austere edge runtime modules."""

from __future__ import annotations

import os
import sys
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.edge_runtime.bearer_broker import (  # noqa: E402
    BearerBroker,
    LinkMetrics,
    LinkType,
    MessageClass,
)
from src.edge_runtime.bootstrap import AustereEdgeRuntime  # noqa: E402
from src.edge_runtime.degradation_controller import DegradationController, OperatingMode  # noqa: E402
from src.edge_runtime.durable_queue import DurableQueue, SyncReconciler  # noqa: E402
from src.edge_runtime.hardware_profiler import HardwareProfiler, HardwareTier, NodeProfile  # noqa: E402
from src.edge_runtime.model_planner import ExecutionAction, ModelExecutionPlanner  # noqa: E402


def _profile(
    tier: HardwareTier = HardwareTier.CPU_STANDARD,
    memory_mb: int = 16384,
    gpu: bool = False,
) -> NodeProfile:
    return NodeProfile(
        tier=tier,
        total_memory_mb=memory_mb,
        cpu_cores=8,
        gpu_available=gpu,
        gpu_name="none" if not gpu else "embedded_nvidia",
        gpu_memory_mb=0 if not gpu else 8192,
        network_interfaces={"eth0": "up"},
    )


def test_hardware_profiler_classifies_node_tiers() -> None:
    profiler = HardwareProfiler()
    assert profiler._classify_tier(8192, False, {"wlan0": "up"}) == HardwareTier.CPU_AUSTERE
    assert profiler._classify_tier(16384, False, {"eth0": "up"}) == HardwareTier.CPU_STANDARD
    assert profiler._classify_tier(16384, True, {"eth0": "up"}) == HardwareTier.EDGE_GPU
    assert profiler._classify_tier(16384, True, {"wwan0": "up"}) == HardwareTier.VEHICLE_NODE
    assert profiler._classify_tier(65536, True, {"eth0": "up"}) == HardwareTier.FIXED_SITE


def test_degradation_controller_mode_transitions_and_service_tiers() -> None:
    controller = DegradationController(_profile(tier=HardwareTier.CPU_AUSTERE, memory_mb=4096))
    assert controller.current_mode == OperatingMode.CPU_CONSTRAINED
    policy = controller.policy()
    assert policy.allow_gpu is False
    assert controller.service_tiers()["command_control"] == 0

    controller.report_link_state(False)
    assert controller.current_mode == OperatingMode.OFFLINE_SURVIVAL
    tiers = controller.service_tiers()
    assert tiers["threat_detection"] == 0
    assert tiers["bulk_sync"] == 2
    assert len(controller.recent_transitions()) >= 2


def test_model_planner_cpu_first_and_offline_summary() -> None:
    profile = _profile(tier=HardwareTier.CPU_STANDARD, memory_mb=4096, gpu=False)
    controller = DegradationController(profile)
    planner = ModelExecutionPlanner(profile, controller)
    plan = planner.plan("phi3", priority=1)
    assert plan.action == ExecutionAction.RUN_LOCAL
    assert plan.selected_variant is not None
    assert plan.selected_variant.requires_gpu is False

    controller.report_link_state(False)
    summary_plan = planner.plan("phi3", priority=2)
    assert summary_plan.action == ExecutionAction.SUMMARIZE_INSTEAD
    unknown = planner.plan("does-not-exist", priority=0)
    assert unknown.action == ExecutionAction.REJECT


def test_bearer_broker_route_and_scoring() -> None:
    broker = BearerBroker()
    broker.update_link(LinkMetrics(LinkType.WIFI, 25.0, 5.0, 0.5, 120.0, True))
    broker.update_link(LinkMetrics(LinkType.CELLULAR, 85.0, 20.0, 1.0, 25.0, True))
    broker.update_link(LinkMetrics(LinkType.WIRED, 10.0, 1.0, 0.1, 1000.0, True))

    decision = broker.route(MessageClass.URGENT_CONTROL)
    assert decision.selected_bearer in {LinkType.WIRED, LinkType.WIFI}
    assert decision.persist_if_fail is True
    assert decision.score > 0
    snapshot = broker.link_snapshot()
    assert snapshot["wifi"]["available"] is True
    assert snapshot["wired"]["score"] >= snapshot["cellular"]["score"]


def test_durable_queue_enqueue_claim_ack_nack_and_reconcile(tmp_path) -> None:
    db_path = str(tmp_path / "queue.db")
    queue = DurableQueue(db_path=db_path)
    first = queue.enqueue("telemetry", {"k": 1})
    second = queue.enqueue("logs", {"k": 2})
    assert first > 0
    assert second > first
    assert queue.stats()["depth"] == 2

    claimed = queue.claim_batch(limit=2)
    assert len(claimed) == 2
    assert claimed[0].attempts == 1
    assert queue.stats()["inflight"] == 2

    queue.nack([claimed[0].id])
    assert queue.stats()["pending"] == 1
    queue.ack([claimed[1].id])
    assert queue.stats()["depth"] == 1

    reconciler = SyncReconciler(queue)
    result = reconciler.run_sync(max_batches=2, batch_size=8)
    assert result["acked"] >= 1
    assert queue.stats()["depth"] == 0
    queue.close()


def test_bootstrap_runtime_initializes_and_status_shape(tmp_path) -> None:
    runtime = AustereEdgeRuntime(queue_db_path=str(tmp_path / "runtime_queue.db"))
    status: Dict[str, object] = runtime.status()
    assert "node_tier" in status
    assert "operating_mode" in status
    assert "bearers" in status
    assert "queue" in status
    runtime.close()


def test_health_surface_contains_policy_and_transitions(tmp_path) -> None:
    runtime = AustereEdgeRuntime(queue_db_path=str(tmp_path / "health_surface_queue.db"))
    payload = runtime.health.full_status()
    assert "policy" in payload
    assert "recent_transitions" in payload
    assert isinstance(payload["recent_transitions"], list)
    runtime.close()


def test_bootstrap_status_helper_returns_runtime_payload() -> None:
    from src.edge_runtime.bootstrap import get_edge_runtime_status

    payload = get_edge_runtime_status()
    assert "node_tier" in payload
    assert "operating_mode" in payload
