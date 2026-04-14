"""Unit tests for air-defense post-miss re-allocation."""

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import (
    Effector,
    EffectorCategory,
    EffectorEnvelope,
    TargetAllocation,
)
from services.air_defense.target_allocator import TargetAllocator


def _effector(
    effector_id: str,
    category: EffectorCategory,
    *,
    readiness: float = 1.0,
    max_range_m: float = 10_000.0,
    max_speed_mps: float | None = None,
) -> Effector:
    return Effector(
        effector_id=effector_id,
        name_en=effector_id.upper(),
        effector_type=category.value,
        category=category,
        echelon="battery-alpha",
        position=(0.0, 0.0, 0.0),
        envelope=EffectorEnvelope(
            min_range_m=0.0,
            max_range_m=max_range_m,
            max_target_speed_mps=max_speed_mps,
            pk_single_shot=0.75,
        ),
        readiness_score=readiness,
        assigned_zone_id="zone-a",
    )


def _allocation(original: Effector, *, fallback_ids: list[str] | None = None) -> TargetAllocation:
    return TargetAllocation(
        target_id="tgt-1",
        target_position=(1_000.0, 0.0, 100.0),
        target_speed_mps=200.0,
        target_classification="cruise_missile",
        effector_id=original.effector_id,
        effector_type=original.effector_type,
        echelon=original.echelon,
        zone_id=original.assigned_zone_id or "",
        slant_range_m=original.range_to((1_000.0, 0.0, 100.0)),
        pk_estimate=0.7,
        suitability_score=0.9,
        reasoning="initial allocation",
        attempts=0,
        max_attempts=3,
        fallback_effector_ids=fallback_ids or [],
    )


def test_report_miss_uses_precomputed_fallback_first() -> None:
    registry = EffectorRegistry()
    drone = _effector("drone-1", EffectorCategory.INTERCEPTOR_DRONE)
    sam = _effector("sam-1", EffectorCategory.SAM_MEDIUM)
    registry.register_many([drone, sam])
    handler = MissHandler(registry, TargetAllocator(registry))
    alloc = _allocation(drone, fallback_ids=["sam-1"])
    drone.begin_engagement(alloc.target_id)

    result = handler.report_miss(alloc)

    assert result.allocated is True
    assert result.allocation is not None
    assert result.allocation.effector_id == "sam-1"
    assert registry.get("drone-1").state.value == "available"  # type: ignore[union-attr]
    assert registry.get("sam-1").state.value == "engaging"  # type: ignore[union-attr]
    assert alloc.attempts == 1
    stats = handler.get_miss_stats()
    assert stats["total_misses"] == 1
    assert stats["targets_with_misses"] == 1


def test_report_miss_falls_back_to_allocator_when_precomputed_unavailable() -> None:
    registry = EffectorRegistry()
    drone = _effector("drone-1", EffectorCategory.INTERCEPTOR_DRONE)
    sam_short = _effector("sam-short-1", EffectorCategory.SAM_SHORT, readiness=0.8)
    ciws = _effector("ciws-1", EffectorCategory.CIWS_GUN, readiness=0.9)
    registry.register_many([drone, sam_short, ciws])
    handler = MissHandler(registry, TargetAllocator(registry))
    alloc = _allocation(drone, fallback_ids=["non-existent"])
    drone.begin_engagement(alloc.target_id)

    result = handler.report_miss(alloc)

    assert result.allocated is True
    assert result.allocation is not None
    # The allocator should select the next viable category from fallback chain.
    assert result.allocation.effector_id == "sam-short-1"
    assert result.reasoning.startswith("Re-allocated")


def test_report_miss_stops_at_max_attempts() -> None:
    registry = EffectorRegistry()
    drone = _effector("drone-1", EffectorCategory.INTERCEPTOR_DRONE)
    registry.register(drone)
    handler = MissHandler(registry, TargetAllocator(registry))
    alloc = _allocation(drone)
    alloc.attempts = 2
    alloc.max_attempts = 3
    drone.begin_engagement(alloc.target_id)

    result = handler.report_miss(alloc)

    assert result.allocated is False
    assert "exceeded max engagement attempts" in result.reasoning
    assert alloc.attempts == 3


def test_report_kill_marks_target_hit_and_releases_effector() -> None:
    registry = EffectorRegistry()
    sam = _effector("sam-1", EffectorCategory.SAM_MEDIUM)
    registry.register(sam)
    handler = MissHandler(registry, TargetAllocator(registry))
    alloc = _allocation(sam)
    sam.begin_engagement(alloc.target_id)

    handler.report_kill(alloc)

    assert alloc.status == "hit"
    assert registry.get("sam-1").state.value == "available"  # type: ignore[union-attr]


def test_guidance_result_miss_triggers_existing_fallback_chain() -> None:
    registry = EffectorRegistry()
    drone = _effector("drone-1", EffectorCategory.INTERCEPTOR_DRONE)
    sam = _effector("sam-1", EffectorCategory.SAM_MEDIUM)
    registry.register_many([drone, sam])
    handler = MissHandler(registry, TargetAllocator(registry))
    alloc = _allocation(drone)
    drone.begin_engagement(alloc.target_id)

    class _GuidanceResult:
        outcome = "MISS"

    result = handler.report_interceptor_guidance_result(alloc, _GuidanceResult())

    assert result is not None
    assert result.allocated is True
    assert result.allocation is not None
    assert result.allocation.effector_id == "sam-1"
    assert alloc.attempts == 1


def test_guidance_result_non_miss_does_not_trigger_fallback() -> None:
    registry = EffectorRegistry()
    drone = _effector("drone-1", EffectorCategory.INTERCEPTOR_DRONE)
    sam = _effector("sam-1", EffectorCategory.SAM_MEDIUM)
    registry.register_many([drone, sam])
    handler = MissHandler(registry, TargetAllocator(registry))
    alloc = _allocation(drone)

    result = handler.report_interceptor_guidance_result(alloc, {"outcome": "hit"})

    assert result is None
    assert alloc.attempts == 0
