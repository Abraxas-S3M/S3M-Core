"""Tests for S3M Edge Autonomy Kernel."""

from src.edge_runtime.autonomy_kernel.bandwidth_router import BandwidthRouter, BandwidthTier
from src.edge_runtime.autonomy_kernel.offline_brain import (
    ConnectivityState,
    OfflineBrain,
)
from src.edge_runtime.autonomy_kernel.priority_allocator import (
    ComputeTask,
    PriorityAllocator,
    TaskPriority,
)


def test_offline_brain_rule_based() -> None:
    brain = OfflineBrain()
    brain.set_connectivity(ConnectivityState.OFFLINE)
    decision = brain.decide(
        {
            "nearest_threat_distance": 30.0,
            "threat_confidence": 0.8,
            "fuel_pct": 60.0,
        }
    )
    assert decision.action == "evade"
    assert decision.method == "rule_based"
    assert decision.connectivity_state == ConnectivityState.OFFLINE


def test_offline_brain_fuel_critical() -> None:
    brain = OfflineBrain()
    decision = brain.decide({"fuel_pct": 10.0})
    assert decision.action == "rtb"


def test_offline_brain_sync_queue() -> None:
    brain = OfflineBrain()
    brain.set_connectivity(ConnectivityState.OFFLINE)
    brain.decide({"nearest_threat_distance": 100.0})
    brain.decide({"nearest_threat_distance": 200.0})
    pending = brain.get_pending_sync()
    assert len(pending) == 2


def test_bandwidth_router_tier_switching() -> None:
    router = BandwidthRouter()
    state = router.update_bandwidth(15.0)
    assert state.tier == BandwidthTier.FULL
    assert router.get_current_model() == "mixtral-8x7b-q4"

    state = router.update_bandwidth(0.5)
    assert state.tier == BandwidthTier.LOW
    assert router.get_current_model() == "distilled-1b-q8"

    state = router.update_bandwidth(0.0)
    assert state.tier == BandwidthTier.ZERO
    assert router.get_current_model() == "rule_based_fallback"


def test_priority_allocator_basic() -> None:
    alloc = PriorityAllocator(total_cores=4.0, total_memory_mb=8192.0)
    result = alloc.submit(
        ComputeTask(name="inference", cpu_cores_needed=2.0, memory_mb_needed=2048.0)
    )
    assert result.allocated is True

    util = alloc.get_utilization()
    assert util["cpu_used"] == 2.0
    assert util["active_tasks"] == 1


def test_priority_allocator_preemption() -> None:
    alloc = PriorityAllocator(total_cores=2.0, total_memory_mb=4096.0)
    low = ComputeTask(
        name="bg_task",
        priority=TaskPriority.LOW,
        cpu_cores_needed=2.0,
        memory_mb_needed=2048.0,
    )
    alloc.submit(low)

    critical = ComputeTask(
        name="threat_assess",
        priority=TaskPriority.CRITICAL,
        cpu_cores_needed=2.0,
        memory_mb_needed=2048.0,
    )
    result = alloc.submit(critical)
    assert result.allocated is True
    assert len(result.preempted_tasks) > 0
