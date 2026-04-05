from __future__ import annotations

from datetime import timedelta

import pytest

from src.platforms.payloads.weapon_adapters import (
    MANPADSAdapter,
    OrionZU23Adapter,
    PayloadAdapter,
    RCWS127Adapter,
    RCWS145Adapter,
    SICHAdapter,
    EngagementError,
    OperatorAuthorization,
    TargetTrack,
    _utc_now,
)


def _auth(*actions: str) -> OperatorAuthorization:
    return OperatorAuthorization(
        operator_id="operator-1",
        authorized_actions=frozenset(actions),
        expires_at=_utc_now() + timedelta(minutes=5),
        command_nonce="nonce-1",
    )


def _track(target_id: str, *, distance_m: float = 1000.0, ir_signature: float = 0.8) -> TargetTrack:
    return TargetTrack(
        target_id=target_id,
        distance_m=distance_m,
        bearing_deg=20.0,
        elevation_deg=2.0,
        velocity_mps=30.0,
        heading_deg=40.0,
        confidence=0.9,
        ir_signature=ir_signature,
    )


def test_rcws127_requires_operator_authorization() -> None:
    adapter = RCWS127Adapter()
    adapter.track_target(_track("trk-1"))
    with pytest.raises(EngagementError):
        adapter.engage_target("trk-1", authorization=None)  # type: ignore[arg-type]


def test_rcws127_engagement_consumes_ammo_and_logs_record() -> None:
    adapter = RCWS127Adapter()
    adapter.track_target(_track("trk-1"))
    record = adapter.engage_target("trk-1", authorization=_auth("engage"), rounds=3)
    assert isinstance(adapter, PayloadAdapter)
    assert record.rounds_expended == 3
    assert adapter.ammo_remaining == 397
    assert len(adapter.engagement_log) == 1


def test_rcws145_blocks_out_of_range_target() -> None:
    adapter = RCWS145Adapter()
    adapter.track_target(_track("trk-1", distance_m=4100.0))
    with pytest.raises(EngagementError, match="outside effective range"):
        adapter.engage_target("trk-1", authorization=_auth("engage"))


def test_sich_requires_distinct_authorizations_for_each_action() -> None:
    adapter = SICHAdapter()
    adapter.track_target(_track("trk-1", distance_m=1200.0))
    with pytest.raises(EngagementError):
        adapter.engage_main_cannon("trk-1", authorization=_auth("engage_coaxial"))

    main = adapter.engage_main_cannon("trk-1", authorization=_auth("engage_main_cannon"), rounds=2)
    coax = adapter.engage_coaxial("trk-1", authorization=_auth("engage_coaxial"), rounds=20)
    smoke = adapter.deploy_smoke(authorization=_auth("deploy_smoke"), salvos=2)
    assert main.rounds_expended == 2
    assert coax.rounds_expended == 20
    assert smoke.action == "deploy_smoke"
    assert adapter.smoke_charges == 4


def test_orion_target_queue_engagement_consumes_expected_burst() -> None:
    adapter = OrionZU23Adapter()
    adapter.track_target(_track("air-1", distance_m=1400.0))
    adapter.queue_target("air-1")
    record = adapter.engage_next_target(authorization=_auth("engage_queue"), burst_seconds=1.0)
    assert record.rounds_expended == 30
    assert adapter.ammo_remaining == 70
    assert not adapter.target_queue


def test_manpads_requires_lock_and_tracks_missile_inventory() -> None:
    adapter = MANPADSAdapter()
    adapter.track_target(_track("uav-1", distance_m=3000.0))
    with pytest.raises(EngagementError, match="IR lock"):
        adapter.launch_missile("uav-1", authorization=_auth("launch_missile"))

    adapter.update_ir_lock("uav-1", lock_quality=0.9)
    adapter.launch_missile("uav-1", authorization=_auth("launch_missile"))
    assert adapter.ammo_remaining == 1


def test_autonomous_fire_release_is_hard_blocked() -> None:
    adapter = RCWS127Adapter()
    with pytest.raises(EngagementError, match="Autonomous fire-release is disabled"):
        adapter.attempt_autonomous_release("trk-x")
