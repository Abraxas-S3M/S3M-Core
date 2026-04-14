"""Unit tests for layered air-defense zone management."""

from __future__ import annotations

import pytest

from services.air_defense.models import DefenseEchelon, DefenseZone
from services.air_defense.zone_manager import ZoneManager


def test_create_standard_echelons_builds_all_doctrinal_layers() -> None:
    manager = ZoneManager()
    zones = manager.create_standard_echelons(center=(0.0, 0.0, 0.0))

    assert len(zones) == 4
    assert {zone.echelon for zone in zones} == {
        DefenseEchelon.CLOSE,
        DefenseEchelon.SHORT,
        DefenseEchelon.MEDIUM,
        DefenseEchelon.EXTENDED,
    }


def test_find_zones_for_target_prefers_outer_layer_first() -> None:
    manager = ZoneManager()
    manager.create_standard_echelons(center=(0.0, 0.0, 0.0))

    # Tactical doctrine prioritizes outer interception for standoff protection.
    zones = manager.find_zones_for_target(target_position=(25_000.0, 0.0, 1_000.0))
    assert [zone.echelon for zone in zones] == [
        DefenseEchelon.EXTENDED,
        DefenseEchelon.MEDIUM,
    ]


def test_assign_effector_to_zone_deduplicates_ids() -> None:
    manager = ZoneManager()
    close_zone = manager.create_standard_echelons(center=(0.0, 0.0, 0.0))[0]

    assert manager.assign_effector_to_zone(close_zone.zone_id, "eff-1")
    assert manager.assign_effector_to_zone(close_zone.zone_id, "eff-1")
    stored = manager.get_zone(close_zone.zone_id)
    assert stored is not None
    assert stored.assigned_effector_ids == ["eff-1"]


def test_get_coverage_report_counts_active_zones_and_effectors() -> None:
    manager = ZoneManager()
    zones = manager.create_standard_echelons(center=(0.0, 0.0, 0.0))
    manager.assign_effector_to_zone(zones[0].zone_id, "close-eff-1")
    manager.assign_effector_to_zone(zones[3].zone_id, "ext-eff-1")
    zones[1].active = False

    report = manager.get_coverage_report()
    assert report["close"]["zones"] == 1
    assert report["close"]["total_effectors"] == 1
    assert report["short"]["zones"] == 0
    assert report["extended"]["total_effectors"] == 1


def test_create_standard_echelons_rejects_invalid_center() -> None:
    manager = ZoneManager()
    with pytest.raises(ValueError):
        manager.create_standard_echelons(center=(0.0, 0.0))


def test_zone_contains_point_checks_altitude_and_radius() -> None:
    zone = DefenseZone(
        name_en="Close test",
        name_ar="اختبار قريب",
        echelon=DefenseEchelon.CLOSE,
        center=(0.0, 0.0, 0.0),
        inner_radius_m=0,
        outer_radius_m=10_000,
        min_altitude_m=0,
        max_altitude_m=3_000,
        priority=1,
    )

    assert zone.contains_point((5_000.0, 0.0, 1_000.0))
    assert not zone.contains_point((15_000.0, 0.0, 1_000.0))
    assert not zone.contains_point((5_000.0, 0.0, 5_000.0))
