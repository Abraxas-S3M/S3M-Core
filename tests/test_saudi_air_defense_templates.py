"""Unit tests for Saudi layered air defense force templates."""

from __future__ import annotations

from collections import Counter

from services.air_defense import DefenseEchelon, EffectorRegistry, ZoneManager, create_krechet_equivalent_unit


def test_create_krechet_equivalent_unit_populates_expected_force_structure() -> None:
    """Template should produce the intended tactical order of battle."""
    registry = EffectorRegistry()
    zone_manager = ZoneManager()

    unit = create_krechet_equivalent_unit(registry=registry, zone_manager=zone_manager)

    assert len(unit.effector_ids) == 22
    assert len(set(unit.effector_ids)) == 22
    assert len(unit.zone_ids) == 4
    assert len(set(unit.zone_ids)) == 4
    assert len(registry.list_all()) == 22

    # Validate echelon distribution for outer-to-inner layered defense.
    zone_by_id = {zone.zone_id: zone for zone in zone_manager.list_zones()}
    counts_by_echelon: Counter[DefenseEchelon] = Counter()
    for effector in registry.list_all():
        zone = zone_by_id[effector.assigned_zone_id]
        counts_by_echelon[zone.echelon] += 1

    assert counts_by_echelon[DefenseEchelon.EXTENDED] == 5
    assert counts_by_echelon[DefenseEchelon.MEDIUM] == 2
    assert counts_by_echelon[DefenseEchelon.SHORT] == 5
    assert counts_by_echelon[DefenseEchelon.CLOSE] == 10


def test_create_krechet_equivalent_unit_tracks_zone_assignments() -> None:
    """Each zone should carry assigned IDs used by battle management logic."""
    registry = EffectorRegistry()
    zone_manager = ZoneManager()
    center = (1200.0, 900.0, 20.0)

    unit = create_krechet_equivalent_unit(
        registry=registry,
        zone_manager=zone_manager,
        center=center,
        defended_asset="Eastern Refinery",
        defended_asset_ar="مصفاة الشرق",
    )

    assert unit.position == center
    assert unit.defended_asset == "Eastern Refinery"
    assert len(unit.zone_ids) == 4

    total_assigned = 0
    for zone_id in unit.zone_ids:
        zone = zone_manager.get_zone(zone_id)
        assert zone is not None
        total_assigned += len(zone.assigned_effector_ids)
        for effector_id in zone.assigned_effector_ids:
            assert registry.get(effector_id) is not None

    assert total_assigned == 22
