"""Smoke test for platform abstraction layer integration.

Military/tactical context:
This suite validates that platform, payload, autonomy, and safety interfaces
compose correctly so command decisions can be executed with guardrails.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.autonomy.engagement_logic import EngagementPipeline
from src.autonomy.mission_executive import MissionExecutive
from src.platforms.common import (
    AuthorityLevel,
    AuthorizationType,
    InterlockState,
    MissionTask,
    MissionTaskType,
    OperatorAuthorization,
    PayloadAdapter,
    PlatformAdapter,
    PlatformState,
    PlatformType,
    ThreatPriority,
    Track,
)
from src.platforms.fixed.horizon_adapter import HorizonAdapter, TrackStore
from src.platforms.payloads.weapon_adapters import (
    MANPADSAdapter,
    OrionZU23Adapter,
    RCWS127Adapter,
    RCWS145Adapter,
    SICHAdapter,
)
from src.platforms.uav.warwar_adapter import WarWarAdapter
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.platforms.usv.g24_adapter import G24Adapter
from src.safety.control_authority import (
    ControlAuthorityService,
    InterlockStateMachine,
    RangeComplianceEngine,
)


def test_platform_adapters_implement_protocol() -> None:
    adapters = [
        HMMWVAdapter("test-hmmwv"),
        WarWarAdapter("test-warwar"),
        G24Adapter("test-g24"),
        HorizonAdapter("test-horizon"),
    ]
    for adapter in adapters:
        assert isinstance(adapter, PlatformAdapter)
        assert adapter.connect()

    assert adapters[0].read_state().platform_type == PlatformType.UGV
    assert adapters[1].launch()
    assert adapters[2].read_state().platform_type == PlatformType.USV
    assert adapters[3].read_state().platform_type == PlatformType.FIXED


def test_payload_adapters_implement_protocol() -> None:
    adapters = [
        RCWS127Adapter("test-rcws127"),
        RCWS145Adapter("test-rcws145"),
        SICHAdapter("test-sich"),
        OrionZU23Adapter("test-orion"),
        MANPADSAdapter("test-manpads"),
    ]
    for adapter in adapters:
        assert isinstance(adapter, PayloadAdapter)
        assert adapter.connect()

    assert adapters[0].read_state().ammo_count == 400

    track = Track(track_id="t1", position=(1000, 500, 200))
    assert adapters[3].queue_target(track)
    assert len(adapters[3].get_queue()) == 1

    auth = OperatorAuthorization(operator_id="cmd-1", auth_type=AuthorizationType.ENGAGE)
    assert adapters[4].operator_authorized_action(auth)
    assert adapters[4].read_state().ammo_count == 1


def test_track_store_ingest_merge_and_age_out() -> None:
    now = datetime.now(timezone.utc)
    store = TrackStore(association_distance_m=100.0, max_track_age_s=5.0)
    t1 = Track(track_id="r1", position=(100, 200, 0), confidence=0.6, last_seen=now)
    t2 = Track(track_id="r2", position=(110, 205, 0), confidence=0.8, last_seen=now)
    stale = Track(
        track_id="r3",
        position=(1000, 1000, 0),
        confidence=0.7,
        last_seen=now - timedelta(seconds=20),
    )

    store.ingest_track(t1)
    store.ingest_track(t2)
    store.ingest_track(stale)

    tracks_before_age = store.get_tracks()
    assert len(tracks_before_age) == 2  # r1+r2 merged, r3 independent
    merged = [track for track in tracks_before_age if track.track_id != "r3"][0]
    assert merged.confidence >= 0.8

    removed = store.age_out(now=now)
    assert removed == 1
    assert len(store.get_tracks()) == 1


def test_engagement_pipeline_evaluates_and_recommends() -> None:
    pipeline = EngagementPipeline()
    tracks = [
        Track(
            track_id="th-1",
            classification="vehicle",
            position=(1000, 0, 0),
            confidence=0.9,
            threat_priority=ThreatPriority.HIGH,
        )
    ]
    recs = pipeline.evaluate_threats(tracks, {"eff-1": None})
    assert len(recs) == 1
    assert recs[0].track_id == "th-1"
    assert recs[0].recommended_effector == "eff-1"
    assert recs[0].roe_compliant is True


def test_mission_executive_patrol_start_and_phase_transitions() -> None:
    executive = MissionExecutive(waypoint_tolerance_m=100.0)
    task = MissionTask(
        task_type=MissionTaskType.PATROL,
        waypoints=[(1000, 0, 0), (2000, 0, 0)],
    )
    assert executive.start_mission(task)
    assert executive.is_active

    state_far = PlatformState(
        platform_id="hmmwv-1",
        platform_type=PlatformType.UGV,
        position=(0, 0, 0),
    )
    cmds_far = executive.update(state_far)
    assert executive.phase == "transit"
    assert len(cmds_far) > 0

    state_near_first_wp = PlatformState(
        platform_id="hmmwv-1",
        platform_type=PlatformType.UGV,
        position=(1000, 0, 0),
    )
    cmds_near = executive.update(state_near_first_wp)
    assert executive.phase == "on-station"
    assert len(cmds_near) > 0


def test_control_authority_tokens_issue_validate_revoke() -> None:
    cas = ControlAuthorityService()
    cas.register_operator("cmd-1", AuthorityLevel.MISSION_COMMANDER)

    auth = cas.issue_authorization("cmd-1", AuthorizationType.ENGAGE)
    assert cas.validate_authorization(auth.auth_id)

    cas.revoke_authorization(auth.auth_id)
    assert not cas.validate_authorization(auth.auth_id)


def test_interlock_state_machine_enforces_transition_order() -> None:
    auth = OperatorAuthorization(operator_id="cmd-1", auth_type=AuthorizationType.ENGAGE)
    ism = InterlockStateMachine("payload-1")

    assert ism.state == InterlockState.SAFE
    assert not ism.transition(InterlockState.FIRING, auth=auth)  # cannot bypass ARMED
    assert ism.transition(InterlockState.ARMED, auth=auth)
    assert ism.state == InterlockState.ARMED
    assert ism.transition(InterlockState.FIRING, auth=auth)
    assert ism.state == InterlockState.FIRING

    ism.emergency_stop()
    assert ism.state == InterlockState.SAFE


def test_range_compliance_engine_enforces_geofences() -> None:
    rce = RangeComplianceEngine()
    rce.add_geofence("allowed-1", [(0, 0), (10000, 0), (10000, 10000), (0, 10000)], "allowed")
    rce.add_geofence("forbidden-1", [(4500, 4500), (5500, 4500), (5500, 5500), (4500, 5500)], "forbidden")

    assert rce.check_position("p1", (1000, 1000, 0))
    assert not rce.check_position("p1", (5000, 5000, 0))
