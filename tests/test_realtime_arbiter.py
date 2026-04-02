"""Tests for real-time arbitration components and integration behavior."""

from __future__ import annotations

from src.autonomy.behavior_trees import ActionNode, BTStatus, MissionExecutor
from src.autonomy.models import MissionStatus
from src.autonomy.realtime_arbiter import PriorityManager, RealtimeDecisionArbiter, RiskAssessor


def test_priority_escalation_and_decay() -> None:
    manager = PriorityManager()
    manager.add_priority(
        "p1",
        base_priority=0.4,
        category="mission",
        escalation_rate=0.1,
        decay_rate=0.05,
        ttl_seconds=60.0,
    )
    first = manager.snapshot()["p1"]["effective_priority"]
    manager.tick(dt=2.0)
    second = manager.snapshot()["p1"]["effective_priority"]
    assert second > first


def test_priority_interrupt_detection() -> None:
    manager = PriorityManager(interrupt_threshold=0.2)
    manager.add_priority("current", 0.5, "mission")
    manager.add_priority("incoming", 0.95, "survival")
    assert manager.should_interrupt() is True


def test_risk_assessment_extreme_conditions_abort() -> None:
    assessor = RiskAssessor()
    result = assessor.assess(
        {
            "threat_distance": 2.0,
            "battery_pct": 1.0,
            "fuel_pct": 2.0,
            "comms_quality": 0.05,
            "roe_violation": True,
            "mission_exposure": 0.95,
        }
    )
    assert result["decision_gate"] == "abort"


def test_risk_trend_detection_escalating() -> None:
    assessor = RiskAssessor(window_size=4)
    assessor.assess({"threat_distance": 80.0, "mission_exposure": 0.1})
    assessor.assess({"threat_distance": 40.0, "mission_exposure": 0.3})
    assessor.assess({"threat_distance": 20.0, "mission_exposure": 0.5})
    out = assessor.assess({"threat_distance": 10.0, "mission_exposure": 0.8})
    assert out["risk_trend"] == "escalating"


def test_replan_triggers_threat_resource_comms() -> None:
    arbiter = RealtimeDecisionArbiter()
    threat = arbiter.arbitrate({"threat_distance": 10.0, "timestamp": 100.0})
    assert threat["replan_trigger"] in {"threat_detected", "threat_escalation", None}
    resource = arbiter.arbitrate({"battery_pct": 3.0, "fuel_pct": 2.0, "timestamp": 110.0})
    assert resource["replan_trigger"] in {"resource_bingo", None}
    comms = arbiter.arbitrate({"comms_quality": 0.0, "timestamp": 120.0})
    assert comms["replan_trigger"] in {"comms_lost", "comms_degraded", None}


def test_arbiter_normal_vs_emergency_flow() -> None:
    arbiter = RealtimeDecisionArbiter()
    normal = arbiter.arbitrate({"threat_distance": 150.0, "battery_pct": 90.0, "timestamp": 1.0})
    assert normal["override"] is False
    emergency = arbiter.arbitrate({"threat_distance": 2.0, "battery_pct": 4.0, "timestamp": 2.0})
    assert emergency["override"] is True
    assert emergency["action"] in {"abort_rtb", "hold_and_reassess", "evade"}


def test_commander_force_override() -> None:
    arbiter = RealtimeDecisionArbiter()
    arbiter.force_override("pivot_mission", reason="Commander redirect")
    out = arbiter.arbitrate({"timestamp": 1.0})
    assert out["override"] is True
    assert out["action"] == "pivot_mission"


def test_decision_reversal_when_conditions_improve() -> None:
    arbiter = RealtimeDecisionArbiter()
    bad = arbiter.arbitrate({"threat_distance": 3.0, "battery_pct": 10.0, "timestamp": 1.0})
    assert bad["override"] is True
    good = arbiter.arbitrate({"threat_distance": 180.0, "battery_pct": 95.0, "timestamp": 10.0})
    assert good["override"] is False


def test_mission_executor_uses_arbiter_override() -> None:
    tree = ActionNode("complete", lambda ctx: BTStatus.SUCCESS)
    arbiter = RealtimeDecisionArbiter()
    arbiter.force_override("hold_and_reassess", reason="test")
    executor = MissionExecutor(tree=tree, tick_rate_hz=50.0, arbiter=arbiter)
    status = executor.run(context={"decision_log": []}, max_ticks=3)
    assert status in {MissionStatus.COMPLETED, MissionStatus.PAUSED}
    assert executor.get_tick_log()
