"""Unit tests for layered air-defense target allocation logic."""

from __future__ import annotations

import pytest

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    AirDefenseZone,
    DefenseEchelon,
    Effector,
    EffectorCategory,
    EffectorEnvelope,
    EffectorState,
    EffectorType,
)
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import ZoneManager


def _zone(zone_id: str, echelon: DefenseEchelon, min_r: float, max_r: float) -> AirDefenseZone:
    return AirDefenseZone(
        zone_id=zone_id,
        name=zone_id,
        echelon=echelon,
        center_position=(0.0, 0.0, 0.0),
        min_radius_m=min_r,
        max_radius_m=max_r,
    )


def _envelope(max_range: float = 6_000.0, pk: float = 0.8) -> EffectorEnvelope:
    return EffectorEnvelope(
        max_range_m=max_range,
        min_range_m=100.0,
        min_altitude_m=0.0,
        max_altitude_m=20_000.0,
        max_target_speed_mps=1_000.0,
        pk_single_shot=pk,
    )


def _effector(
    effector_id: str,
    zone_id: str,
    category: EffectorCategory,
    echelon: DefenseEchelon,
    position=(0.0, 0.0, 0.0),
    readiness=0.9,
    max_range=6_000.0,
) -> Effector:
    return Effector(
        effector_id=effector_id,
        name_en=effector_id,
        effector_type=EffectorType.SAM_PANTSIR,
        category=category,
        echelon=echelon,
        state=EffectorState.READY,
        zone_id=zone_id,
        position=position,
        envelope=_envelope(max_range=max_range),
        readiness_score=readiness,
        ammunition_total=4,
        ammunition_remaining=4,
    )


def test_allocate_returns_unallocated_outside_all_zones() -> None:
    allocator = TargetAllocator(
        registry=EffectorRegistry([]),
        zone_manager=ZoneManager([_zone("short", DefenseEchelon.SHORT, 0.0, 1_500.0)]),
    )

    result = allocator.allocate(
        target_id="t-1",
        target_position=(5_000.0, 0.0, 500.0),
        target_speed_mps=150.0,
        target_classification="ENEMY_UAV",
    )

    assert result.allocated is False
    assert "outside all defense zones" in result.reasoning.lower()


def test_allocate_prefers_preferred_category_for_uav() -> None:
    zone = _zone("medium", DefenseEchelon.MEDIUM, 0.0, 5_000.0)
    interceptor = _effector(
        "int-1",
        zone.zone_id,
        EffectorCategory.INTERCEPTOR_DRONE,
        DefenseEchelon.MEDIUM,
    )
    sam = _effector(
        "sam-1",
        zone.zone_id,
        EffectorCategory.SAM_SHORT,
        DefenseEchelon.MEDIUM,
    )
    allocator = TargetAllocator(
        registry=EffectorRegistry([interceptor, sam]),
        zone_manager=ZoneManager([zone]),
    )

    result = allocator.allocate(
        target_id="t-uav",
        target_position=(3_000.0, 0.0, 700.0),
        target_speed_mps=180.0,
        target_classification="ENEMY_UAV",
    )

    assert result.allocated is True
    assert result.allocation is not None
    assert result.allocation.effector_id == "int-1"


def test_allocate_skips_unreachable_effectors() -> None:
    zone = _zone("short", DefenseEchelon.SHORT, 0.0, 8_000.0)
    too_short = _effector(
        "ciws-near",
        zone.zone_id,
        EffectorCategory.CIWS_GUN,
        DefenseEchelon.SHORT,
        max_range=1_000.0,
    )
    capable = _effector(
        "sam-capable",
        "remote-zone",
        EffectorCategory.SAM_MEDIUM,
        DefenseEchelon.MEDIUM,
        max_range=10_000.0,
    )
    allocator = TargetAllocator(
        registry=EffectorRegistry([too_short, capable]),
        zone_manager=ZoneManager([zone]),
    )

    result = allocator.allocate(
        target_id="t-cruise",
        target_position=(4_500.0, 0.0, 800.0),
        target_speed_mps=250.0,
        target_classification="ENEMY_CRUISE_MISSILE",
    )

    assert result.allocated is True
    assert result.allocation is not None
    assert result.allocation.effector_id == "sam-capable"


def test_allocate_marks_engagement_and_records_log() -> None:
    zone = _zone("extended", DefenseEchelon.EXTENDED, 0.0, 9_000.0)
    lead = _effector(
        "lead",
        zone.zone_id,
        EffectorCategory.SAM_MEDIUM,
        DefenseEchelon.EXTENDED,
        readiness=0.95,
    )
    alt1 = _effector(
        "alt1",
        zone.zone_id,
        EffectorCategory.SAM_SHORT,
        DefenseEchelon.SHORT,
        readiness=0.7,
    )
    alt2 = _effector(
        "alt2",
        zone.zone_id,
        EffectorCategory.CIWS_GUN,
        DefenseEchelon.CLOSE,
        readiness=0.6,
    )
    allocator = TargetAllocator(
        registry=EffectorRegistry([lead, alt1, alt2]),
        zone_manager=ZoneManager([zone]),
    )

    result = allocator.allocate(
        target_id="t-aircraft",
        target_position=(3_500.0, 0.0, 900.0),
        target_speed_mps=220.0,
        target_classification="ENEMY_AIRCRAFT",
    )

    assert result.allocated is True
    assert lead.state == EffectorState.ENGAGED
    assert lead.ammunition_remaining == 3
    assert result.allocation is not None
    assert len(result.allocation.fallback_effector_ids) <= 3
    assert len(set(result.allocation.fallback_effector_ids)) == len(
        result.allocation.fallback_effector_ids
    )
    assert allocator.get_allocation_log(limit=1)[0].target_id == "t-aircraft"


def test_allocate_validates_negative_target_speed() -> None:
    allocator = TargetAllocator(
        registry=EffectorRegistry([]),
        zone_manager=ZoneManager([_zone("short", DefenseEchelon.SHORT, 0.0, 2_000.0)]),
    )

    with pytest.raises(ValueError):
        allocator.allocate(
            target_id="bad",
            target_position=(100.0, 0.0, 50.0),
            target_speed_mps=-1.0,
            target_classification="UNKNOWN",
        )
