"""Unit tests for HOOL autonomy extension.

Military context:
Tests verify autonomy envelope guardrails and safe-mode behavior for tactical
platforms operating without real-time human control.
"""

from datetime import datetime, timedelta, timezone

from services.autonomy.hool_extension.envelope_checker import EnvelopeChecker
from services.autonomy.hool_extension.hool_agent import HOOLAgent
from services.autonomy.hool_extension.models import CompanionCompute, MissionEnvelope, PlatformClass
from services.autonomy.hool_extension.platform_packager import PlatformPackager


def _envelope() -> MissionEnvelope:
    now = datetime.now(timezone.utc)
    return MissionEnvelope(
        envelope_id="ENV-1",
        mission_id="MSN-1",
        approved_by="CMD",
        approved_at=now,
        geofence_vertices=[(0.0, 0.0, 10.0), (1.0, 0.0, 10.0), (1.0, 1.0, 10.0), (0.0, 1.0, 10.0)],
        geofence_ceiling_m=200.0,
        geofence_floor_m=0.0,
        time_window=(now - timedelta(minutes=1), now + timedelta(minutes=60)),
        roe_level="weapons_tight",
        max_targets=3,
        allowed_target_types=["ENEMY_UAV"],
        min_engagement_confidence=0.8,
        min_battery_pct=20.0,
        min_fuel_pct=10.0,
        max_comms_loss_seconds=120.0,
        max_risk_score=75.0,
        max_escalation_level=3,
        custom_constraints={},
    )


def test_mission_envelope_creation_and_validation():
    env = _envelope()
    ok, issues = env.validate()
    assert ok is True
    assert issues == []


def test_envelope_checker_detects_geofence_violation():
    env = _envelope()
    checker = EnvelopeChecker(env)
    violation = checker.check_geofence((5.0, 5.0, 50.0))
    assert violation is not None
    assert violation.dimension == "geofence"
    assert violation.severity == "critical"


def test_envelope_checker_detects_energy_critical():
    env = _envelope()
    checker = EnvelopeChecker(env)
    violation = checker.check_energy(1.0, 1.0)
    assert violation is not None
    assert violation.dimension == "energy"
    assert violation.severity in {"warning", "critical"}


def test_envelope_checker_detects_comms_loss():
    env = _envelope()
    checker = EnvelopeChecker(env)
    violation = checker.check_comms(200.0)
    assert violation is not None
    assert violation.dimension == "comms"
    assert violation.severity == "critical"


def test_hool_agent_tick_returns_decision_with_audit_trail():
    env = _envelope()
    agent = HOOLAgent(platform_class=PlatformClass.UAV_QUADROTOR, envelope=env)
    decision = agent.tick({"position": (0.5, 0.5, 100.0), "battery_pct": 90.0, "risk_score": 30.0})
    assert decision.decision_id
    assert "audit_entry_id" in decision.action_taken
    assert "xai" in decision.action_taken


def test_transition_to_safe_mode_per_platform_type():
    env = _envelope()
    air = HOOLAgent(PlatformClass.UAV_QUADROTOR, env)
    ground = HOOLAgent(PlatformClass.UGV_WHEELED, env)
    sea = HOOLAgent(PlatformClass.USV_SURFACE, env)
    assert air.transition_to_safe_mode("test")["details"]["platform_action"] == "cease_offense_climb_loiter"
    assert ground.transition_to_safe_mode("test")["details"]["platform_action"] == "cease_offense_stop_defensive_posture"
    assert sea.transition_to_safe_mode("test")["details"]["platform_action"] == "cease_offense_all_stop_maintain_heading"


def test_platform_packager_generates_correct_manifest_for_jetson_vs_pi():
    env = _envelope()
    packager = PlatformPackager()
    jetson_pkg = packager.package_for_platform(PlatformClass.UAV_FIXED_WING, env)
    pi_pkg = packager.package_for_platform(PlatformClass.UUV_UNDERWATER, env)
    assert any("phi3" in m.lower() for m in jetson_pkg["models"])
    assert not any("phi3" in m.lower() for m in pi_pkg["models"])


def test_companion_compute_for_platform_returns_correct_specs():
    spec = CompanionCompute.for_platform(PlatformClass.UAV_QUADROTOR)
    assert "Jetson" in spec.cpu_model or "Raspberry" in spec.cpu_model
    assert spec.python_version == "3.11"
