"""Comprehensive tests for S3M air defense effector registry and zone manager.

Military context:
Verifies Krechet-equivalent fire distribution, echelon engagement priority,
miss-handler fallback chains, and Saudi template deployments.
"""

import sys

sys.path.insert(0, ".")

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import (
    DefenseEchelon,
    DefenseZone,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
    EngagementEnvelope,
)
from services.air_defense.saudi_templates import create_krechet_equivalent_unit
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import ZoneManager


def _make_sam() -> Effector:
    return Effector(
        name_en="Test SAM",
        name_ar="صاروخ تجريبي",
        effector_type=EffectorType.BUK_FS,
        category=EffectorCategory.SAM_MEDIUM,
        echelon=DefenseEchelon.MEDIUM,
        envelope=EngagementEnvelope(
            min_range_m=3000,
            max_range_m=40000,
            min_altitude_m=15,
            max_altitude_m=25000,
            pk_single_shot=0.80,
        ),
        position=(0, 0, 0),
        ammunition_total=4,
        ammunition_remaining=4,
    )


def _make_gun() -> Effector:
    return Effector(
        name_en="Test Gun",
        name_ar="مدفع تجريبي",
        effector_type=EffectorType.SKYNEX,
        category=EffectorCategory.CIWS_GUN,
        echelon=DefenseEchelon.CLOSE,
        envelope=EngagementEnvelope(
            min_range_m=200,
            max_range_m=4000,
            min_altitude_m=5,
            max_altitude_m=3000,
            pk_single_shot=0.55,
        ),
        position=(0, 0, 0),
        ammunition_total=200,
        ammunition_remaining=200,
    )


# --- EngagementEnvelope Tests ---


def test_envelope_target_in_range():
    env = EngagementEnvelope(
        min_range_m=500,
        max_range_m=10000,
        min_altitude_m=10,
        max_altitude_m=5000,
    )
    assert env.target_in_envelope(5000, 500) is True
    assert env.target_in_envelope(100, 500) is False  # too close
    assert env.target_in_envelope(5000, 6000) is False  # too high


def test_envelope_speed_limit():
    env = EngagementEnvelope(
        min_range_m=100,
        max_range_m=10000,
        min_altitude_m=0,
        max_altitude_m=5000,
        max_target_speed_mps=300,
    )
    assert env.target_in_envelope(5000, 1000, target_speed_mps=200) is True
    assert env.target_in_envelope(5000, 1000, target_speed_mps=400) is False


# --- Effector Tests ---


def test_effector_readiness_and_availability():
    eff = _make_sam()
    assert eff.is_available is True
    assert eff.readiness_score > 0.5
    eff.ammunition_remaining = 0
    assert eff.is_available is False


def test_effector_engagement_lifecycle():
    eff = _make_sam()
    eff.begin_engagement("target-1")
    assert eff.state == EffectorState.ENGAGING
    assert eff.current_target_id == "target-1"
    eff.complete_engagement(kill=True)
    assert eff.state == EffectorState.READY
    assert eff.kills_confirmed == 1
    assert eff.ammunition_remaining == 3


def test_effector_can_engage_checks_geometry():
    eff = _make_sam()  # max range 40km
    assert eff.can_engage((20000, 0, 500)) is True  # 20km, 500m alt
    assert eff.can_engage((50000, 0, 500)) is False  # 50km, out of range
    assert eff.can_engage((20000, 0, 30000)) is False  # 30km alt, out of envelope


# --- Registry Tests ---


def test_registry_register_and_query():
    reg = EffectorRegistry()
    sam = _make_sam()
    gun = _make_gun()
    reg.register(sam)
    reg.register(gun)
    assert reg.count() == 2
    mediums = reg.query(echelon=DefenseEchelon.MEDIUM)
    assert len(mediums) == 1
    assert mediums[0].effector_type == EffectorType.BUK_FS


def test_registry_available_for_target():
    reg = EffectorRegistry()
    sam = _make_sam()
    gun = _make_gun()
    reg.register(sam)
    reg.register(gun)
    # Target at 25km range, 1000m altitude -- only SAM can reach
    candidates = reg.get_available_for_target((25000, 0, 1000))
    assert len(candidates) == 1
    assert candidates[0].category == EffectorCategory.SAM_MEDIUM


# --- Zone Manager Tests ---


def test_zone_contains_point():
    zone = DefenseZone(
        echelon=DefenseEchelon.SHORT,
        center=(0, 0, 0),
        inner_radius_m=10000,
        outer_radius_m=20000,
        min_altitude_m=0,
        max_altitude_m=8000,
    )
    assert zone.contains_point((15000, 0, 500)) is True  # 15km range
    assert zone.contains_point((5000, 0, 500)) is False  # 5km, inside inner radius


def test_standard_echelons_created():
    zm = ZoneManager()
    zones = zm.create_standard_echelons((0, 0, 0))
    assert len(zones) == 4
    echelons = {z.echelon for z in zones}
    assert DefenseEchelon.CLOSE in echelons
    assert DefenseEchelon.MEDIUM in echelons


def test_find_zones_for_target():
    zm = ZoneManager()
    zm.create_standard_echelons((0, 0, 0))
    # Target at 15km -- should be in SHORT zone
    zones = zm.find_zones_for_target((15000, 0, 500))
    assert any(z.echelon == DefenseEchelon.SHORT for z in zones)


# --- Target Allocator Tests ---


def test_allocator_assigns_best_effector():
    reg = EffectorRegistry()
    zm = ZoneManager()
    zones = zm.create_standard_echelons((0, 0, 0))
    sam = _make_sam()
    sam.assigned_zone_id = [z for z in zones if z.echelon == DefenseEchelon.MEDIUM][0].zone_id
    reg.register(sam)
    zm.assign_effector_to_zone(sam.assigned_zone_id, sam.effector_id)

    allocator = TargetAllocator(reg, zm)
    result = allocator.allocate("tgt-1", (25000, 0, 1000), 100, "ENEMY_UAV")
    assert result.allocated is True
    assert result.allocation.effector_id == sam.effector_id


def test_allocator_rejects_out_of_zone_target():
    reg = EffectorRegistry()
    zm = ZoneManager()
    zm.create_standard_echelons((0, 0, 0))
    allocator = TargetAllocator(reg, zm)
    result = allocator.allocate("tgt-far", (100000, 0, 500), 50, "ENEMY_UAV")
    assert result.allocated is False


# --- Miss Handler Tests ---


def test_miss_handler_reallocates_to_fallback():
    reg = EffectorRegistry()
    zm = ZoneManager()
    zones = zm.create_standard_echelons((0, 0, 0))
    medium_zone = [z for z in zones if z.echelon == DefenseEchelon.MEDIUM][0]
    close_zone = [z for z in zones if z.echelon == DefenseEchelon.CLOSE][0]

    sam = _make_sam()
    sam.assigned_zone_id = medium_zone.zone_id
    reg.register(sam)
    zm.assign_effector_to_zone(medium_zone.zone_id, sam.effector_id)

    gun = _make_gun()
    gun.assigned_zone_id = close_zone.zone_id
    reg.register(gun)
    zm.assign_effector_to_zone(close_zone.zone_id, gun.effector_id)

    allocator = TargetAllocator(reg, zm)
    miss_handler = MissHandler(reg, allocator)

    # First allocation at 25km -> SAM
    result1 = allocator.allocate("tgt-2", (25000, 0, 1000), 100, "ENEMY_UAV")
    assert result1.allocated is True

    # Target moves closer to 3km, SAM misses -> gun should pick up
    result2 = miss_handler.report_miss(
        result1.allocation,
        updated_target_position=(3000, 0, 500),
        updated_target_speed=80,
    )
    assert result2.allocated is True
    assert result2.allocation.effector_id == gun.effector_id


# --- Saudi Template Tests ---


def test_krechet_equivalent_unit_creation():
    reg = EffectorRegistry()
    zm = ZoneManager()
    unit = create_krechet_equivalent_unit(reg, zm, center=(0, 0, 0))
    assert len(unit.effector_ids) == 22  # 2+3+4+6+5+2
    assert len(unit.zone_ids) == 4
    stats = reg.get_stats()
    assert stats["total"] == 22
    assert stats["ready"] == 22
    coverage = zm.get_coverage_report()
    assert coverage["medium"]["total_effectors"] >= 2
    assert coverage["extended"]["total_effectors"] >= 5


if __name__ == "__main__":
    test_envelope_target_in_range()
    test_envelope_speed_limit()
    test_effector_readiness_and_availability()
    test_effector_engagement_lifecycle()
    test_effector_can_engage_checks_geometry()
    test_registry_register_and_query()
    test_registry_available_for_target()
    test_zone_contains_point()
    test_standard_echelons_created()
    test_find_zones_for_target()
    test_allocator_assigns_best_effector()
    test_allocator_rejects_out_of_zone_target()
    test_miss_handler_reallocates_to_fallback()
    test_krechet_equivalent_unit_creation()
    print("ALL AIR DEFENSE TESTS PASSED")

