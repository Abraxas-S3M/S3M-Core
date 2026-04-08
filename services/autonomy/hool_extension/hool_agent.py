"""HOOL autonomous agent running on edge companion computers.

Military context:
This agent executes autonomous mission behavior under strict envelope controls,
assurance guardrails, and tamper-evident audit logging for command accountability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from services.autonomy.hool_extension.envelope_checker import EnvelopeChecker
from services.autonomy.hool_extension.hool_behavior_tree import HOOLBehaviorTree
from services.autonomy.hool_extension.models import (
    CompanionCompute,
    HOOLDecision,
    HOOLMissionState,
    MissionEnvelope,
    PlatformClass,
)
from src.autonomy.models import DecisionType
from src.autonomy.xai import AssuranceChecker, DecisionExplainer
from src.navigation.edge_inference.edge_llm_runner import EdgeLLMRunner
from src.security.crypto import SecureAuditLog


class HOOLAgent:
    """Envelope-constrained autonomous mission executor for HOOL operations."""

    def __init__(self, platform_class: PlatformClass, envelope: MissionEnvelope):
        self.platform_class = platform_class
        self.envelope = envelope
        self.companion = CompanionCompute.for_platform(platform_class)
        self.envelope_checker = EnvelopeChecker(envelope)
        self.behavior_tree = HOOLBehaviorTree(checker=self.envelope_checker, llm_capable=self.companion.llm_capable)
        self.assurance_checker = AssuranceChecker(risk_threshold=0.7, confidence_threshold=0.3)
        self.decision_explainer = DecisionExplainer()
        self.audit_log = SecureAuditLog(log_dir="data/security_audit/hool")
        self.decision_history: List[Dict[str, Any]] = []
        self.edge_llm = EdgeLLMRunner(max_memory_mb=min(8192.0, float(self.companion.ram_mb))) if self.companion.llm_capable else None
        if self.edge_llm is not None:
            self.edge_llm.load()

        start_dt, end_dt = envelope.time_window
        self.state = HOOLMissionState(
            mission_id=envelope.mission_id,
            platform_class=platform_class,
            envelope=envelope,
            current_position=envelope.geofence_vertices[0],
            battery_pct=100.0,
            fuel_pct=100.0,
            comms_status="nominal",
            targets_engaged=0,
            time_remaining_s=max((end_dt - start_dt).total_seconds(), 0.0),
            risk_score=0.0,
            violations=[],
            mode="autonomous",
        )

    def _update_state_from_sensor(self, sensor_data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self.state.current_position = tuple(sensor_data.get("position", self.state.current_position))
        self.state.battery_pct = float(sensor_data.get("battery_pct", self.state.battery_pct))
        self.state.fuel_pct = float(sensor_data.get("fuel_pct", self.state.fuel_pct))
        self.state.comms_status = sensor_data.get("comms_status", self.state.comms_status)
        self.state.targets_engaged = int(sensor_data.get("targets_engaged", self.state.targets_engaged))
        self.state.risk_score = float(sensor_data.get("risk_score", self.state.risk_score))
        self.state.proposed_escalation_level = int(sensor_data.get("proposed_escalation_level", self.state.proposed_escalation_level))
        self.state.proposed_action = str(sensor_data.get("proposed_action", self.state.proposed_action))
        target = sensor_data.get("target", {})
        self.state.target_type = target.get("type") if isinstance(target, dict) else None
        self.state.target_confidence = float(target.get("confidence", 0.0)) if isinstance(target, dict) else 0.0
        self.state.time_remaining_s = max((self.envelope.time_window[1] - now).total_seconds(), 0.0)

    def _trace_payload(self, action: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        return {
            "trace_backend": "langfuse_phoenix_offline_stub",
            "trace_id": trace_id,
            "span": "hool_decision_tick",
            "action": action,
        }

    def tick(self, sensor_data: dict) -> HOOLDecision:
        """Run one autonomy cycle: envelope-check, decision, assurance, XAI, audit."""
        self._update_state_from_sensor(sensor_data)
        all_pass, violations = self.envelope_checker.check_all(self.state)
        self.state.violations = violations

        critical = [v for v in violations if v.severity == "critical"]
        warnings = [v for v in violations if v.severity == "warning"]
        if critical:
            self.state.mode = "safe_mode"
            proposed_action = self.transition_to_safe_mode(critical[0].recommended_action)
        elif warnings:
            self.state.mode = "autonomous"
            proposed_action = self.behavior_tree.tick(self.state, {**sensor_data, "rtb_bias": True})
        elif all_pass:
            self.state.mode = "autonomous"
            proposed_action = self.behavior_tree.tick(self.state, sensor_data)
        else:
            self.state.mode = "loiter"
            proposed_action = {"action": "loiter", "details": {"reason": "non_critical_envelope_violation"}}

        decision_type = DecisionType.HOLD
        action_name = str(proposed_action.get("action", "hold")).lower()
        if "engage" in action_name:
            decision_type = DecisionType.ENGAGE
            self.state.targets_engaged += 1
        elif "rtb" in action_name:
            decision_type = DecisionType.DELEGATE
            self.state.mode = "rtb"
        elif "safe" in action_name:
            decision_type = DecisionType.RETREAT

        risk_norm = max(0.0, min(1.0, self.state.risk_score / 100.0 if self.state.risk_score > 1 else self.state.risk_score))
        decision = HOOLDecision(
            decision_id=f"hool-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            decision_type=decision_type,
            agent_id=f"{self.platform_class.value}-agent",
            mission_id=self.state.mission_id,
            context={
                "mode": self.state.mode,
                "position": self.state.current_position,
                "battery_pct": self.state.battery_pct,
                "comms_status": self.state.comms_status,
                "rules_of_engagement": self.envelope.roe_level,
                "violations": [v.dimension for v in violations],
                "trace": self._trace_payload(proposed_action),
            },
            action_taken=proposed_action,
            alternatives_considered=[
                {"option": "rtb", "reason": "safety fallback"},
                {"option": "loiter", "reason": "awaiting clearer state"},
            ],
            confidence=0.82 if not critical else 0.95,
            reasoning="Envelope-bounded autonomous decision produced by HOOL behavior tree.",
            llm_consulted=bool(self.edge_llm is not None),
            requires_human_review=False,
            risk_score=risk_norm,
            envelope_check={
                "all_pass": all_pass,
                "violations": [v.__dict__ for v in violations],
            },
            platform_class=self.platform_class,
            companion_compute=self.companion.cpu_model,
            autonomous_level=self.state.proposed_escalation_level,
        )

        assurance = self.assurance_checker.check(decision)
        xai = self.decision_explainer.explain(decision)
        audit_entry = self.audit_log.log(
            action="hool_decision",
            severity="WARNING" if critical else "INFO",
            source="hool_agent",
            details={
                "decision": decision.to_audit_entry(),
                "assurance": assurance,
                "xai_summary": xai.get("summary"),
                "violations": [v.__dict__ for v in violations],
            },
        )

        decision.action_taken["assurance"] = assurance
        decision.action_taken["xai"] = xai
        decision.action_taken["audit_entry_id"] = audit_entry.get("entry_id")
        self.decision_history.append(decision.to_dict())
        if len(self.decision_history) > 2000:
            self.decision_history = self.decision_history[-2000:]
        return decision

    def execute_lost_link(self) -> dict:
        """Run deterministic lost-link behavior for denied-communications scenarios."""
        return {
            "procedure": "lost_link",
            "steps": [
                "loiter_for_60_seconds",
                "attempt_recontact_on_primary_and_backup_links",
                "rtb_via_safest_route",
                "land_or_surface_in_place_if_energy_critical",
            ],
        }

    def transition_to_safe_mode(self, reason: str) -> dict:
        """Immediately shift platform to non-offensive safety posture."""
        self.state.mode = "safe_mode"
        if self.platform_class in {PlatformClass.UAV_QUADROTOR, PlatformClass.UAV_FIXED_WING, PlatformClass.UAV_VTOL}:
            detail = "cease_offense_climb_loiter"
        elif self.platform_class in {PlatformClass.UGV_WHEELED, PlatformClass.UGV_TRACKED}:
            detail = "cease_offense_stop_defensive_posture"
        else:
            detail = "cease_offense_all_stop_maintain_heading"
        self.audit_log.log(
            action="hool_safe_mode_transition",
            severity="WARNING",
            source="hool_agent",
            details={"reason": reason, "platform_action": detail},
        )
        return {"action": "safe_mode", "details": {"reason": reason, "platform_action": detail}}

    def get_platform_manifest(self) -> dict:
        """Return deployable HOOL package specification for this platform."""
        base_packages = [
            "fastapi",
            "uvicorn",
            "numpy",
            "pydantic",
            "pyyaml",
        ]
        models = ["yolov8n.onnx"] if self.companion.gpu_available else []
        if self.companion.llm_capable:
            models.append("phi3-medium-int4.gguf")
        est_mem = 1500.0 + (900.0 if self.companion.llm_capable else 200.0)
        return {
            "platform": self.platform_class.value,
            "cpu": self.companion.cpu_model,
            "python_packages": base_packages,
            "model_files": models,
            "config_files": ["hool_agent.yaml", "mission_envelope.json"],
            "estimated_memory_usage_mb": est_mem,
            "ram_budget_mb": self.companion.ram_mb,
        }
