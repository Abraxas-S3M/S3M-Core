"""Unit tests for S3M air defense data models.

Military context:
These tests validate tactical geometry gates and effector readiness transitions
that protect fire-control assignment quality in layered air defense operations.
"""

from datetime import datetime, timezone

import pytest

from services.air_defense.models import (
    DefenseEchelon,
    DefenseZone,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
    EngagementEnvelope,
    TargetAllocation,
)


def test_engagement_envelope_rejects_invalid_ranges_and_pk():
    with pytest.raises(ValueError):
        EngagementEnvelope(
            min_range_m=2_000,
            max_range_m=1_000,
            min_altitude_m=0,
            max_altitude_m=1_000,
        )
    with pytest.raises(ValueError):
        EngagementEnvelope(
            min_range_m=100,
            max_range_m=1_000,
            min_altitude_m=100,
            max_altitude_m=10,
        )
    with pytest.raises(ValueError):
        EngagementEnvelope(
            min_range_m=100,
            max_range_m=1_000,
            min_altitude_m=0,
            max_altitude_m=1_000,
            pk_single_shot=1.2,
        )


def test_target_in_envelope_checks_range_altitude_speed_and_wrapped_azimuth():
    envelope = EngagementEnvelope(
        min_range_m=500,
        max_range_m=5_000,
        min_altitude_m=10,
        max_altitude_m=3_000,
        min_azimuth_deg=330.0,
        max_azimuth_deg=30.0,
        max_target_speed_mps=200.0,
    )

    assert envelope.target_in_envelope(1_200, 500, 150, 350) is True
    assert envelope.target_in_envelope(1_200, 500, 150, 10) is True
    assert envelope.target_in_envelope(1_200, 500, 250, 350) is False
    assert envelope.target_in_envelope(300, 500, 100, 350) is False
    assert envelope.target_in_envelope(1_200, 3_500, 100, 350) is False
    assert envelope.target_in_envelope(1_200, 500, 100, 90) is False


def test_effector_string_enums_are_coerced_and_can_engage():
    envelope = EngagementEnvelope(
        min_range_m=100,
        max_range_m=2_000,
        min_altitude_m=0,
        max_altitude_m=2_000,
    )
    effector = Effector(
        effector_id="eff-alpha",
        effector_type="franken_sam",
        category="sam_short",
        echelon="short",
        state="ready",
        envelope=envelope,
        position=(0.0, 0.0, 0.0),
        ammunition_total=4,
        ammunition_remaining=4,
    )

    assert effector.effector_type == EffectorType.FRANKEN_SAM
    assert effector.category == EffectorCategory.SAM_SHORT
    assert effector.echelon == DefenseEchelon.SHORT
    assert effector.state == EffectorState.READY
    assert effector.is_available is True
    assert effector.can_engage((500.0, 0.0, 200.0), target_speed_mps=150.0) is True


def test_effector_engagement_state_machine_updates_counts_and_ammo():
    effector = Effector(
        effector_id="eff-bravo",
        state=EffectorState.READY,
        ammunition_total=1,
        ammunition_remaining=1,
    )

    effector.begin_engagement("tgt-1")
    assert effector.state == EffectorState.ENGAGING
    assert effector.current_target_id == "tgt-1"
    assert effector.engagement_start is not None

    effector.complete_engagement(kill=True)
    assert effector.engagements_completed == 1
    assert effector.kills_confirmed == 1
    assert effector.ammunition_remaining == 0
    assert effector.current_target_id is None
    assert effector.engagement_start is None
    assert effector.state == EffectorState.RELOADING
    assert effector.is_available is False


def test_defense_zone_contains_point_with_sector_wraparound():
    zone = DefenseZone(
        zone_id="zone-1",
        echelon=DefenseEchelon.SHORT,
        center=(0.0, 0.0, 0.0),
        inner_radius_m=500,
        outer_radius_m=4_000,
        min_altitude_m=50,
        max_altitude_m=2_000,
        min_azimuth_deg=330.0,
        max_azimuth_deg=30.0,
    )

    assert zone.contains_point((0.0, 1_000.0, 200.0)) is True  # north (0 deg)
    assert zone.contains_point((-1_000.0, 0.0, 200.0)) is False  # west (270 deg)
    assert zone.contains_point((0.0, 200.0, 200.0)) is False  # inside inner radius
    assert zone.contains_point((0.0, 1_000.0, 2_500.0)) is False  # above altitude


def test_target_allocation_to_dict_rounds_numeric_fields():
    allocation = TargetAllocation(
        target_id="tgt-9",
        effector_id="eff-charlie",
        effector_type=EffectorType.BUK_M1,
        echelon=DefenseEchelon.MEDIUM,
        slant_range_m=12_345.678,
        pk_estimate=0.87654,
        suitability_score=0.76543,
        timestamp=datetime.now(timezone.utc),
        attempts=1,
    )

    payload = allocation.to_dict()
    assert payload["target_id"] == "tgt-9"
    assert payload["effector_id"] == "eff-charlie"
    assert payload["effector_type"] == "buk_m1"
    assert payload["echelon"] == "medium"
    assert payload["slant_range_m"] == 12_345.7
    assert payload["pk_estimate"] == 0.877
    assert payload["suitability_score"] == 0.765
