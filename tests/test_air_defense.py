"""Unit tests for air-defense effector registry and zone manager subsystem.

Military context:
Tests verify deterministic layered-defense behavior so command nodes can trust
allocation and fallback logic during high-tempo air engagements.
"""

from __future__ import annotations

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import (
    DefenseEchelon,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
    EngagementEnvelope,
    TargetAllocation,
)
from services.air_defense.saudi_templates import build_saudi_air_defense_unit
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import DefenseZoneManager


def _make_effector(
    effector_id: str,
    *,
    zone_id: str,
    echelon: DefenseEchelon,
    category: EffectorCategory,
    effector_type: EffectorType,
    min_range: float,
    max_range: float,
    ammo: int = 8,
    readiness: float = 1.0,
    priority: int = 20,
    position=(0.0, 0.0, 0.0),
) -> Effector:
    return Effector(
        effector_id=effector_id,
        name_en=f"{effector_id}-en",
        name_ar=f"{effector_id}-ar",
        effector_type=effector_type,
        category=category,
        echelon=echelon,
        envelope=EngagementEnvelope(
            min_range_km=min_range,
            max_range_km=max_range,
            min_altitude_m=0.0,
            max_altitude_m=15000.0,
        ),
        state=EffectorState(
            readiness=readiness,
            ammunition_current=ammo,
            ammunition_capacity=max(ammo, 1),
            reload_time_seconds=0.0,
        ),
        zone_id=zone_id,
        position=position,
        priority=priority,
    )


def _build_stack():
    registry = EffectorRegistry()
    zones = DefenseZoneManager()
    zones.create_echeloned_zones(
        unit_id="unit-1",
        center=(0.0, 0.0),
        name_prefix_en="Unit 1",
        name_prefix_ar="Unit 1",
    )
    allocator = TargetAllocator(registry=registry, zone_manager=zones)
    miss_handler = MissHandler(allocator=allocator, registry=registry)
    return registry, zones, allocator, miss_handler


def test_models_validate_basic_constraints():
    try:
        EngagementEnvelope(
            min_range_km=20.0,
            max_range_km=10.0,
            min_altitude_m=0.0,
            max_altitude_m=1000.0,
        )
        assert False, "expected invalid envelope range to raise ValueError"
    except ValueError:
        pass

    try:
        EffectorState(
            readiness=0.9,
            ammunition_current=10,
            ammunition_capacity=5,
            reload_time_seconds=3.0,
        )
        assert False, "expected invalid ammo state to raise ValueError"
    except ValueError:
        pass


def test_registry_register_query_and_ammunition_updates():
    registry, zones, _, _ = _build_stack()
    medium_zone = zones.list_zones(echelon=DefenseEchelon.MEDIUM)[0]
    effector = _make_effector(
        "eff-medium-1",
        zone_id=medium_zone.zone_id,
        echelon=DefenseEchelon.MEDIUM,
        category=EffectorCategory.MISSILE,
        effector_type=EffectorType.PATRIOT_PAC3,
        min_range=20.0,
        max_range=40.0,
    )
    registry.register_effector(effector)
    ready = registry.query_effectors(echelon=DefenseEchelon.MEDIUM, ready_only=True)
    assert len(ready) == 1
    assert ready[0].effector_id == "eff-medium-1"

    assert registry.consume_ammunition("eff-medium-1", rounds=3)
    assert registry.get_effector("eff-medium-1").state.ammunition_current == 5

    registry.update_ammunition("eff-medium-1", 0)
    assert registry.get_effector("eff-medium-1").state.ammunition_current == 0


def test_zone_manager_point_checks_and_echelon_classification():
    _, zones, _, _ = _build_stack()
    assert zones.classify_echelon_for_distance(8.0) == DefenseEchelon.CLOSE
    assert zones.classify_echelon_for_distance(14.0) == DefenseEchelon.SHORT
    assert zones.classify_echelon_for_distance(35.0) == DefenseEchelon.MEDIUM

    close_zone = zones.list_zones(echelon=DefenseEchelon.CLOSE)[0]
    assert zones.point_in_zone(3.0, 2.0, 100.0, close_zone.zone_id)
    assert not zones.point_in_zone(18.0, 0.0, 100.0, close_zone.zone_id)


def test_zone_overlap_reports_positive_value_for_intersecting_zones():
    zones = DefenseZoneManager()
    zones.create_echeloned_zones(unit_id="u1", center=(0.0, 0.0), name_prefix_en="U1", name_prefix_ar="U1")
    zones.create_echeloned_zones(unit_id="u2", center=(6.0, 0.0), name_prefix_en="U2", name_prefix_ar="U2")
    overlap = zones.compute_coverage_overlap("u1-close-zone", "u2-close-zone", sample_resolution=60)
    assert overlap["overlap_km2"] > 0.0
    assert 0.0 < overlap["overlap_ratio"] <= 1.0


def test_allocator_prefers_outer_echelon_when_available():
    registry, zones, allocator, _ = _build_stack()
    medium_zone = zones.list_zones(echelon=DefenseEchelon.MEDIUM)[0]
    short_zone = zones.list_zones(echelon=DefenseEchelon.SHORT)[0]

    registry.register_effector(
        _make_effector(
            "eff-medium",
            zone_id=medium_zone.zone_id,
            echelon=DefenseEchelon.MEDIUM,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.PATRIOT_PAC3,
            min_range=20.0,
            max_range=40.0,
        )
    )
    registry.register_effector(
        _make_effector(
            "eff-short",
            zone_id=short_zone.zone_id,
            echelon=DefenseEchelon.SHORT,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.NASAMS_AMRAAM,
            min_range=10.0,
            max_range=20.0,
        )
    )

    result = allocator.allocate_target(
        target_id="tgt-1",
        target_position=(25.0, 0.0, 1000.0),
        target_type="enemy_uav",
    )
    assert result.selected_allocation is not None
    assert result.selected_allocation.assigned_effector_id == "eff-medium"
    assert result.selected_allocation.echelon == DefenseEchelon.MEDIUM


def test_allocator_falls_back_when_outer_echelon_unavailable():
    registry, zones, allocator, _ = _build_stack()
    medium_zone = zones.list_zones(echelon=DefenseEchelon.MEDIUM)[0]
    short_zone = zones.list_zones(echelon=DefenseEchelon.SHORT)[0]
    registry.register_effector(
        _make_effector(
            "eff-medium-empty",
            zone_id=medium_zone.zone_id,
            echelon=DefenseEchelon.MEDIUM,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.THAAD,
            min_range=20.0,
            max_range=40.0,
            ammo=0,
        )
    )
    registry.register_effector(
        _make_effector(
            "eff-short-ready",
            zone_id=short_zone.zone_id,
            echelon=DefenseEchelon.SHORT,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.SPYDER_SR,
            min_range=10.0,
            max_range=20.0,
        )
    )

    result = allocator.allocate_target(
        target_id="tgt-2",
        target_position=(15.0, 0.0, 800.0),
        target_type="enemy_missile",
    )
    assert result.selected_allocation is not None
    assert result.selected_allocation.assigned_effector_id == "eff-short-ready"


def test_allocator_batch_applies_queue_pressure_for_multi_target_load():
    registry, zones, allocator, _ = _build_stack()
    medium_zone = zones.list_zones(echelon=DefenseEchelon.MEDIUM)[0]
    registry.register_effector(
        _make_effector(
            "eff-medium-a",
            zone_id=medium_zone.zone_id,
            echelon=DefenseEchelon.MEDIUM,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.SAMP_T,
            min_range=20.0,
            max_range=40.0,
        )
    )
    registry.register_effector(
        _make_effector(
            "eff-medium-b",
            zone_id=medium_zone.zone_id,
            echelon=DefenseEchelon.MEDIUM,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.HAWK_XXI,
            min_range=20.0,
            max_range=40.0,
        )
    )

    results = allocator.allocate_many(
        [
            {"target_id": "tgt-a", "target_position": (25.0, 0.0, 1200.0), "target_type": "enemy_uav"},
            {"target_id": "tgt-b", "target_position": (25.0, 1.0, 1200.0), "target_type": "enemy_uav"},
        ]
    )
    assert results[0].selected_allocation is not None
    assert results[1].selected_allocation is not None
    first_eff = results[0].selected_allocation.assigned_effector_id
    second_eff = results[1].selected_allocation.assigned_effector_id
    assert first_eff != second_eff


def test_miss_handler_drone_miss_prefers_missile_channel():
    registry, zones, allocator, miss_handler = _build_stack()
    close_zone = zones.list_zones(echelon=DefenseEchelon.CLOSE)[0]

    registry.register_effector(
        _make_effector(
            "missile-short",
            zone_id=close_zone.zone_id,
            echelon=DefenseEchelon.CLOSE,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.NASAMS_AMRAAM,
            min_range=1.0,
            max_range=20.0,
        )
    )
    registry.register_effector(
        _make_effector(
            "gun-close",
            zone_id=close_zone.zone_id,
            echelon=DefenseEchelon.CLOSE,
            category=EffectorCategory.GUN,
            effector_type=EffectorType.SKYGUARD_35MM,
            min_range=0.2,
            max_range=6.0,
        )
    )

    prior = TargetAllocation(
        allocation_id="alloc-prev-1",
        target_id="tgt-drone-1",
        target_type="enemy_uav",
        target_position=(3.0, 0.0, 500.0),
        assigned_effector_id="gun-close",
        echelon=DefenseEchelon.CLOSE,
        score=50.0,
        reason="initial gun shot",
        queued_index=1,
        fallback_depth=0,
        created_at=1.0,
    )
    reallocation = miss_handler.handle_miss(
        target_id="tgt-drone-1",
        target_position=(3.0, 0.0, 500.0),
        target_type="enemy_uav",
        previous_allocation=prior,
        miss_reason="drone_miss",
    )
    assert reallocation.selected_allocation is not None
    assert reallocation.selected_allocation.assigned_effector_id == "missile-short"


def test_miss_handler_missile_miss_falls_back_to_gun_or_manpads():
    registry, zones, allocator, miss_handler = _build_stack()
    short_zone = zones.list_zones(echelon=DefenseEchelon.SHORT)[0]
    close_zone = zones.list_zones(echelon=DefenseEchelon.CLOSE)[0]
    registry.register_effector(
        _make_effector(
            "missile-short-2",
            zone_id=short_zone.zone_id,
            echelon=DefenseEchelon.SHORT,
            category=EffectorCategory.MISSILE,
            effector_type=EffectorType.SPYDER_SR,
            min_range=1.0,
            max_range=20.0,
        )
    )
    registry.register_effector(
        _make_effector(
            "manpads-close",
            zone_id=close_zone.zone_id,
            echelon=DefenseEchelon.CLOSE,
            category=EffectorCategory.MANPADS,
            effector_type=EffectorType.STINGER_MANPADS,
            min_range=0.5,
            max_range=5.0,
        )
    )

    prior = TargetAllocation(
        allocation_id="alloc-prev-2",
        target_id="tgt-missile-1",
        target_type="enemy_missile",
        target_position=(4.0, 0.0, 700.0),
        assigned_effector_id="missile-short-2",
        echelon=DefenseEchelon.SHORT,
        score=66.0,
        reason="initial missile shot",
        queued_index=1,
        fallback_depth=0,
        created_at=1.0,
    )
    result = miss_handler.handle_miss(
        target_id="tgt-missile-1",
        target_position=(4.0, 0.0, 700.0),
        target_type="enemy_missile",
        previous_allocation=prior,
        miss_reason="missile_miss",
    )
    assert result.selected_allocation is not None
    assert result.selected_allocation.assigned_effector_id == "manpads-close"


def test_saudi_template_contains_multiechelon_bilingual_effectors():
    unit = build_saudi_air_defense_unit(unit_id="template-test", center=(0.0, 0.0))
    assert len(unit.effectors) >= 17
    assert len(unit.zones) == 3
    assert {zone.echelon for zone in unit.zones} == {DefenseEchelon.CLOSE, DefenseEchelon.SHORT, DefenseEchelon.MEDIUM}
    assert all(effector.name_en and effector.name_ar for effector in unit.effectors)
