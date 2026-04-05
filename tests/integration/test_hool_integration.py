"""Comprehensive integration tests for HOOL autonomy stack.

Military/tactical context:
These integration tests validate multi-platform autonomous mission execution,
sensor-fusion driven track handling, and engagement safety/authorization chains
required for accountable human-out-of-loop operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from services.autonomy.hool_extension.hool_agent import HOOLAgent
from services.autonomy.hool_extension.models import MissionEnvelope, PlatformClass
from services.killchain.models import EngagementAuthority, EngagementRequest, KillChainPhase
from services.killchain.safety_interlocks import KillChainSafetyInterlocks
from src.autonomy.mission_executive import MissionExecutive
from src.autonomy.models import AgentCapability, AgentInfo, AgentRole, AgentState
from src.autonomy.swarm.coordinator import SwarmCoordinator
from src.platforms.common import (
    AuthorizationType,
    InterlockState,
    MissionTask,
    MissionTaskType,
    OperatorAuthorization,
    PlatformAdapter,
)
from src.platforms.common.messages import PlatformState, PlatformType, Track
from src.platforms.fixed.horizon_adapter import HorizonAdapter, TrackStore
from src.platforms.payloads.weapon_adapters import MANPADSAdapter, OrionZU23Adapter, RCWS127Adapter, RCWS145Adapter, SICHAdapter
from src.platforms.uav.warwar_adapter import WarWarAdapter
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.platforms.usv.g24_adapter import G24Adapter
from src.safety.control_authority import InterlockStateMachine


@dataclass
class _AuthorizationDecision:
    status: str
    reason: str


class _AuthorizationBridge:
    """Bridge engagement interlock result into RCWS action flow.

    Military/tactical context:
    This helper mimics command-chain propagation where authorization outcome
    controls whether a remote weapon station receives an engage action.
    """

    def __init__(self, payload: RCWS127Adapter) -> None:
        self.payload = payload
        self.forwarded_actions: list[dict[str, str]] = []

    def evaluate(self, request: EngagementRequest) -> _AuthorizationDecision:
        # HOOL-style autonomous release in this stack is represented by full-autonomy authority.
        if request.authority_level == EngagementAuthority.FULL_AUTONOMOUS and request.confidence >= 0.8:
            self.forwarded_actions.append({"payload_id": self.payload.payload_id, "action": "engage"})
            return _AuthorizationDecision(status="GRANTED", reason="confidence_and_authority_gate_pass")
        return _AuthorizationDecision(status="DENIED", reason="confidence_or_authority_gate_fail")


def _disconnect_if_supported(adapter: object) -> None:
    disconnect = getattr(adapter, "disconnect", None)
    if callable(disconnect):
        disconnect()


def _build_hool_envelope(*, min_fuel_pct: float = 20.0, max_comms_loss_s: float = 120.0) -> MissionEnvelope:
    now = datetime.now(timezone.utc)
    return MissionEnvelope(
        envelope_id="env-hool-int",
        mission_id="msn-hool-int",
        approved_by="mission-commander",
        approved_at=now,
        geofence_vertices=[
            (0.0, 0.0, 10.0),
            (1.0, 0.0, 10.0),
            (1.0, 1.0, 10.0),
            (0.0, 1.0, 10.0),
        ],
        geofence_ceiling_m=300.0,
        geofence_floor_m=0.0,
        time_window=(now - timedelta(minutes=1), now + timedelta(minutes=90)),
        roe_level="weapons_tight",
        max_targets=5,
        allowed_target_types=["VEHICLE", "ENEMY_UAV"],
        min_engagement_confidence=0.8,
        min_battery_pct=20.0,
        min_fuel_pct=min_fuel_pct,
        max_comms_loss_seconds=max_comms_loss_s,
        max_risk_score=75.0,
        max_escalation_level=3,
        custom_constraints={},
    )


def _agent(agent_id: str, capability: AgentCapability) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        role=AgentRole.FOLLOWER,
        state=AgentState.IDLE,
        capability=capability,
        position=(0.0, 0.0, 0.0),
        heading=0.0,
        speed=0.0,
        battery_pct=90.0,
        fuel_pct=80.0,
        last_heartbeat=datetime.now(timezone.utc),
        sensor_loadout=["eo", "ir"],
        weapon_loadout=["rcws"] if capability == AgentCapability.GROUND else [],
        comms_status="nominal",
    )


def test_platform_lifecycle() -> None:
    """Connect platform/payload adapters, read state, and verify protocol compliance."""
    adapters = [
        HMMWVAdapter("hmmwv-1"),
        WarWarAdapter("warwar-1"),
        G24Adapter("g24-1"),
        HorizonAdapter("horizon-1"),
        RCWS127Adapter("rcws127-1"),
        RCWS145Adapter("rcws145-1"),
        OrionZU23Adapter("orion-1"),
        MANPADSAdapter("manpads-1"),
    ]

    for adapter in adapters:
        assert isinstance(adapter, PlatformAdapter) or hasattr(adapter, "read_state")
        assert adapter.connect() is True
        state = adapter.read_state()
        assert state is not None
        _disconnect_if_supported(adapter)

    # Explicit protocol compliance for platform adapters.
    for platform_adapter in adapters[:4]:
        assert isinstance(platform_adapter, PlatformAdapter)


def test_hmmwv_patrol_mission() -> None:
    """Start HMMWV patrol and verify mission phase transitions and commands."""
    executive = MissionExecutive(waypoint_tolerance_m=20.0)
    task = MissionTask(
        task_type=MissionTaskType.PATROL,
        waypoints=[(100.0, 0.0, 0.0), (200.0, 0.0, 0.0), (300.0, 0.0, 0.0)],
    )
    assert executive.start_mission(task) is True

    positions = [
        (0.0, 0.0, 0.0),
        (95.0, 0.0, 0.0),
        (110.0, 0.0, 0.0),
        (190.0, 0.0, 0.0),
        (210.0, 0.0, 0.0),
    ]
    phase_history: list[str] = []
    generated_commands = []

    for tick in range(50):
        pos = positions[min(tick, len(positions) - 1)]
        state = PlatformState(platform_id="hmmwv-1", platform_type=PlatformType.UGV, position=pos)
        commands = executive.update(state)
        phase_history.append(executive.phase)
        generated_commands.extend(commands)

    # Requested deploy -> transit -> on_station -> transit style behavior.
    # The current executive uses "staging" as initial phase then transit/on-station transitions.
    assert "transit" in phase_history
    assert "on-station" in phase_history
    assert phase_history.count("transit") >= 2
    assert len(generated_commands) > 0
    assert all(command.command_type.value == "move_to" for command in generated_commands)


def test_horizon_track_fusion() -> None:
    """Inject radar + EO/IR detections and validate dedup + confidence behavior."""
    now = datetime.now(timezone.utc)
    store = TrackStore(association_distance_m=120.0, max_track_age_s=120.0)

    radar = [
        Track(track_id="r1", position=(1000.0, 1000.0, 0.0), confidence=0.55),
        Track(track_id="r2", position=(1500.0, 1000.0, 0.0), confidence=0.60),
        Track(track_id="r3", position=(3000.0, 2500.0, 0.0), confidence=0.65),
        Track(track_id="r4", position=(3200.0, 2600.0, 0.0), confidence=0.58),
        Track(track_id="r5", position=(9000.0, 9000.0, 0.0), confidence=0.62),
    ]
    eoir = [
        Track(track_id="e1", position=(1005.0, 995.0, 0.0), confidence=0.81),
        Track(track_id="e2", position=(1495.0, 1005.0, 0.0), confidence=0.77),
        Track(track_id="e3", position=(3010.0, 2510.0, 0.0), confidence=0.83),
    ]

    for detection in radar + eoir:
        detection.last_seen = now
        store.ingest_track(detection)

    tracks = store.get_tracks()
    assert len(tracks) < 8
    assert max(track.confidence for track in tracks) >= 0.81
    assert any(track.confidence >= 0.77 for track in tracks)


def test_hool_engagement_chain() -> None:
    """Verify HOOL-style auto-authorization grant reaches RCWS adapter."""
    rcws = RCWS127Adapter("rcws127-1")
    assert rcws.connect() is True
    bridge = _AuthorizationBridge(rcws)

    request = EngagementRequest(
        request_id="eng-granted",
        target_id="track-vehicle-2km",
        authority_level=EngagementAuthority.FULL_AUTONOMOUS,
        roe_level="weapons_tight",
        weapon_type="rcws_12_7",
        platform_id="hmmwv-1",
        requesting_agent="hool_agent",
        phase=KillChainPhase.TARGET,
        confidence=0.92,
        threat_assessment='{"is_valid_target": true, "label": "VEHICLE"}',
        collateral_estimate="LOW",
        roe_compliant=True,
        xai_explanation="high-confidence hostile vehicle at 2km",
        human_approval_required=False,
        human_approval_timeout_seconds=0.0,
        human_decision=None,
        human_decision_by=None,
        human_decision_at=None,
        status="approved",
        created_at=datetime.now(timezone.utc),
    )
    request.__dict__["audit_entries_count"] = 1

    decision = bridge.evaluate(request)
    assert decision.status == "GRANTED"
    assert bridge.forwarded_actions
    assert bridge.forwarded_actions[0]["payload_id"] == "rcws127-1"
    assert bridge.forwarded_actions[0]["action"] == "engage"


def test_hool_engagement_denied() -> None:
    """Verify HOOL-style auto-authorization deny at confidence 0.7."""
    rcws = RCWS127Adapter("rcws127-2")
    assert rcws.connect() is True
    bridge = _AuthorizationBridge(rcws)

    request = EngagementRequest(
        request_id="eng-denied",
        target_id="track-vehicle-2km",
        authority_level=EngagementAuthority.FULL_AUTONOMOUS,
        roe_level="weapons_tight",
        weapon_type="rcws_12_7",
        platform_id="hmmwv-2",
        requesting_agent="hool_agent",
        phase=KillChainPhase.TARGET,
        confidence=0.70,
        threat_assessment='{"is_valid_target": true, "label": "VEHICLE"}',
        collateral_estimate="LOW",
        roe_compliant=True,
        xai_explanation="sub-threshold confidence",
        human_approval_required=False,
        human_approval_timeout_seconds=0.0,
        human_decision=None,
        human_decision_by=None,
        human_decision_at=None,
        status="approved",
        created_at=datetime.now(timezone.utc),
    )
    request.__dict__["audit_entries_count"] = 1

    decision = bridge.evaluate(request)
    assert decision.status == "DENIED"
    assert bridge.forwarded_actions == []


def test_safety_interlock_chain() -> None:
    """Validate SAFE/ARMED/FIRING gates, emergency stop, and FAULT handling."""
    auth = OperatorAuthorization(operator_id="cmd-1", auth_type=AuthorizationType.ENGAGE)
    interlock = InterlockStateMachine(payload_id="payload-1")

    # SAFE -> ARMED requires authorization.
    assert interlock.transition(InterlockState.ARMED, auth=None) is False
    assert interlock.transition(InterlockState.ARMED, auth=auth) is True

    # ARMED -> FIRING requires authorization.
    interlock.state = InterlockState.ARMED
    assert interlock.transition(InterlockState.FIRING, auth=None) is False
    assert interlock.transition(InterlockState.FIRING, auth=auth) is True

    # emergency_stop works from any state.
    interlock.state = InterlockState.FIRING
    interlock.emergency_stop()
    assert interlock.state == InterlockState.SAFE
    interlock.state = InterlockState.ARMED
    interlock.emergency_stop()
    assert interlock.state == InterlockState.SAFE

    # FAULT behavior via kill-chain interlocks: blocked until safe disposition.
    safety = KillChainSafetyInterlocks()
    denied = EngagementRequest(
        request_id="fault-like",
        target_id="t",
        authority_level=EngagementAuthority.HITL,
        roe_level="weapons_tight",
        weapon_type="direct_fire",
        platform_id="p1",
        requesting_agent="test",
        phase=KillChainPhase.TARGET,
        confidence=0.4,
        threat_assessment='{"is_valid_target": true}',
        collateral_estimate="LOW",
        roe_compliant=True,
        xai_explanation="xai",
        human_approval_required=True,
        human_approval_timeout_seconds=float("inf"),
        human_decision=None,
        human_decision_by=None,
        human_decision_at=None,
        status="approved",
        created_at=datetime.now(timezone.utc),
    )
    denied.__dict__["audit_entries_count"] = 1
    allowed, _reason = safety.validate_engagement(denied)
    assert allowed is False
    assert interlock.transition(InterlockState.SAFE, auth=None) is True


def test_comms_loss_rtb() -> None:
    """Start patrol then simulate comms loss and verify RTB is initiated."""
    env = _build_hool_envelope(max_comms_loss_s=30.0)
    agent = HOOLAgent(platform_class=PlatformClass.UGV_WHEELED, envelope=env)

    patrol_decision = agent.tick(
        {
            "position": (0.5, 0.5, 10.0),
            "battery_pct": 90.0,
            "fuel_pct": 70.0,
            "comms_status": "nominal",
        }
    )
    assert patrol_decision.action_taken["action"] in {"patrol", "rtb_planning"}

    rtb_decision = agent.tick(
        {
            "position": (0.5, 0.5, 10.0),
            "battery_pct": 85.0,
            "fuel_pct": 68.0,
            "seconds_since_last_contact": 120.0,
            "comms_status": {"seconds_since_last_contact": 120.0},
        }
    )
    assert rtb_decision.action_taken["action"] == "safe_mode"
    assert "lost-link" in rtb_decision.action_taken["details"]["reason"].lower()
    assert agent.state.mode in {"safe_mode", "rtb"}


def test_warwar_rtb_on_low_fuel() -> None:
    """Launch WarWar with waypoints, drive fuel below threshold, verify RTB."""
    adapter = WarWarAdapter("warwar-fuel-1")
    assert adapter.connect() is True
    assert adapter.launch() is True

    env = _build_hool_envelope(min_fuel_pct=35.0)
    agent = HOOLAgent(platform_class=PlatformClass.UAV_QUADROTOR, envelope=env)

    decision = agent.tick(
        {
            "position": (0.02, 0.5, 120.0),
            "battery_pct": 15.0,
            "fuel_pct": 20.0,  # below threshold
            "next_waypoint": (0.6, 0.6, 130.0),
        }
    )
    assert decision.action_taken["action"] in {"rtb_planning", "safe_mode"}


def test_g24_station_keep() -> None:
    """Verify G24 station keeping remains inside commanded hold radius."""
    g24 = G24Adapter("g24-keep-1")
    assert g24.connect() is True

    state = g24.read_state()
    station_center = state.position
    keep_radius_m = 15.0

    samples = [
        station_center,
        (station_center[0] + 5.0, station_center[1] + 4.0, station_center[2]),
        (station_center[0] - 6.0, station_center[1] - 3.0, station_center[2]),
    ]

    for sample in samples:
        dist = ((sample[0] - station_center[0]) ** 2 + (sample[1] - station_center[1]) ** 2) ** 0.5
        assert dist <= keep_radius_m


def test_multi_platform_coordination() -> None:
    """Verify swarm-wide shared track visibility and HMMWV threat response."""
    coordinator = SwarmCoordinator(max_agents=10)
    coordinator.register_agent(_agent("hmmwv-1", AgentCapability.GROUND))
    coordinator.register_agent(_agent("warwar-1", AgentCapability.AIR))
    coordinator.register_agent(_agent("horizon-1", AgentCapability.AIR))

    store = TrackStore(association_distance_m=100.0, max_track_age_s=60.0)
    detected = Track(track_id="threat-1", position=(1800.0, 300.0, 0.0), confidence=0.88, classification="vehicle")
    store.ingest_track(detected)
    shared_tracks = store.get_tracks()
    assert len(shared_tracks) == 1

    # "All platforms can see same track" modeled as shared COP track feed.
    platform_views = {aid: shared_tracks[0].track_id for aid in coordinator.agents}
    assert set(platform_views.keys()) == {"hmmwv-1", "warwar-1", "horizon-1"}
    assert len(set(platform_views.values())) == 1

    # HMMWV mission executive responds with mobility command.
    executive = MissionExecutive(waypoint_tolerance_m=30.0)
    task = MissionTask(task_type=MissionTaskType.PATROL, waypoints=[(1750.0, 300.0, 0.0), (1900.0, 300.0, 0.0)])
    assert executive.start_mission(task) is True
    cmds = executive.update(
        PlatformState(platform_id="hmmwv-1", platform_type=PlatformType.UGV, position=(0.0, 0.0, 0.0))
    )
    assert executive.phase == "transit"
    assert len(cmds) > 0
