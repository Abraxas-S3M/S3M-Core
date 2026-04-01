"""Lightweight HOOL behavior tree optimized for edge companion compute.

Military context:
This tree prioritizes survivability and ROE-compliant autonomy for disconnected
operations by using deterministic fallback logic when compute is constrained.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from services.autonomy.hool_extension.envelope_checker import EnvelopeChecker
from services.autonomy.hool_extension.models import HOOLMissionState, PlatformClass


@dataclass
class _NodeResult:
    action: str
    details: Dict[str, Any]
    success: bool = True


class HOOLPatrolNode:
    """Patrol within geofence and trigger RTB planning near boundaries."""

    def run(self, state: HOOLMissionState, sensor_data: Dict[str, Any]) -> _NodeResult:
        margin = float(sensor_data.get("boundary_margin", 0.05))
        lat, lon, _ = state.current_position
        lats = [v[0] for v in state.envelope.geofence_vertices]
        lons = [v[1] for v in state.envelope.geofence_vertices]
        near_edge = (
            (lat - min(lats)) <= margin
            or (max(lats) - lat) <= margin
            or (lon - min(lons)) <= margin
            or (max(lons) - lon) <= margin
        )
        if near_edge:
            return _NodeResult("rtb_planning", {"reason": "approaching_geofence_boundary"})
        return _NodeResult("patrol", {"waypoint": sensor_data.get("next_waypoint")})


class HOOLEngageNode:
    """Engage only when ROE and confidence checks pass."""

    def run(self, state: HOOLMissionState, sensor_data: Dict[str, Any]) -> _NodeResult:
        target = sensor_data.get("target", {})
        target_type = str(target.get("type", "UNKNOWN"))
        confidence = float(target.get("confidence", 0.0))
        if confidence < state.envelope.min_engagement_confidence:
            return _NodeResult("hold_fire", {"reason": "confidence_below_threshold", "confidence": confidence}, False)
        allowed = {t.upper() for t in state.envelope.allowed_target_types}
        if allowed and target_type.upper() not in allowed:
            return _NodeResult("hold_fire", {"reason": "target_type_not_allowed", "target_type": target_type}, False)
        return _NodeResult("engage", {"target": target, "confidence": confidence})


class HOOLReconNode:
    """Recon behavior with optional ATR depending on edge compute capability."""

    def run(self, state: HOOLMissionState, sensor_data: Dict[str, Any], llm_capable: bool) -> _NodeResult:
        if llm_capable:
            return _NodeResult("recon_atr", {"sensor": sensor_data.get("sensor", "eo_ir")})
        return _NodeResult("recon_passive", {"reason": "limited_compute_rule_mode"})


class HOOLRTBNode:
    """Return-to-base behavior under envelope-aware route constraints."""

    def run(self, state: HOOLMissionState, sensor_data: Dict[str, Any]) -> _NodeResult:
        return _NodeResult("rtb", {"route": sensor_data.get("rtb_route", "safest_geofence_route")})


class HOOLSafeModeNode:
    """Emergency safe-mode action based on platform class."""

    def run(self, state: HOOLMissionState, reason: str) -> _NodeResult:
        if state.platform_class in {PlatformClass.UAV_QUADROTOR, PlatformClass.UAV_FIXED_WING, PlatformClass.UAV_VTOL}:
            action = "climb_and_loiter"
        elif state.platform_class in {PlatformClass.UGV_WHEELED, PlatformClass.UGV_TRACKED}:
            action = "halt_and_defensive_posture"
        else:
            action = "all_stop_maintain_heading"
        return _NodeResult("safe_mode", {"platform_action": action, "reason": reason})


class HOOLLostLinkNode:
    """Lost-link deterministic fallback sequence for disconnected operations."""

    def run(self, state: HOOLMissionState) -> _NodeResult:
        return _NodeResult(
            "lost_link_procedure",
            {
                "steps": [
                    "loiter_60_seconds",
                    "attempt_recontact",
                    "rtb_safest_route",
                    "land_or_surface_if_rtb_impossible",
                ]
            },
        )


class EnvelopeGuardDecorator:
    """Decorator that short-circuits node execution on critical violations."""

    def __init__(self, checker: EnvelopeChecker):
        self.checker = checker

    def wrap(self, state: HOOLMissionState, proposed: _NodeResult) -> _NodeResult:
        _, violations = self.checker.check_all(state)
        critical = [v for v in violations if v.severity == "critical"]
        if critical:
            return _NodeResult(
                "safe_mode",
                {
                    "reason": "envelope_guard_critical_violation",
                    "violations": [v.dimension for v in critical],
                },
                False,
            )
        return proposed


class HOOLBehaviorTree:
    """Selector/sequence style BT with envelope-aware tactical routing."""

    def __init__(self, checker: EnvelopeChecker, llm_capable: bool):
        self.checker = checker
        self.llm_capable = llm_capable
        self.patrol = HOOLPatrolNode()
        self.engage = HOOLEngageNode()
        self.recon = HOOLReconNode()
        self.rtb = HOOLRTBNode()
        self.safe_mode = HOOLSafeModeNode()
        self.lost_link = HOOLLostLinkNode()
        self.guard = EnvelopeGuardDecorator(checker)

    def tick(self, state: HOOLMissionState, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one lightweight behavior-tree tick."""
        critical_violations = [v for v in state.violations if v.severity == "critical"]
        if critical_violations:
            result = self.safe_mode.run(state, reason=critical_violations[0].recommended_action)
            return {"action": result.action, "details": result.details}

        seconds_since_contact = sensor_data.get("seconds_since_last_contact", 0.0)
        if float(seconds_since_contact) > state.envelope.max_comms_loss_seconds:
            result = self.lost_link.run(state)
            return {"action": result.action, "details": result.details}

        target = sensor_data.get("target")
        if target:
            result = self.engage.run(state, sensor_data)
            guarded = self.guard.wrap(state, result)
            return {"action": guarded.action, "details": guarded.details}

        if bool(sensor_data.get("recon_mission", False)):
            result = self.recon.run(state, sensor_data, llm_capable=self.llm_capable)
            guarded = self.guard.wrap(state, result)
            return {"action": guarded.action, "details": guarded.details}

        patrol_result = self.patrol.run(state, sensor_data)
        guarded_patrol = self.guard.wrap(state, patrol_result)
        if guarded_patrol.action == "safe_mode":
            return {"action": "rtb", "details": {"reason": "guard_forced_rtb"}}
        return {"action": guarded_patrol.action, "details": guarded_patrol.details}
