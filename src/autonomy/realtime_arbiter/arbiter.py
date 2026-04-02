"""Realtime decision arbitration for mid-action override and reversal."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .priority_manager import PriorityManager
from .replan_engine import OnlineReplanner
from .risk_assessor import RiskAssessor


class RealtimeDecisionArbiter:
    """Tick-time arbiter for abort/replan/interrupt override control."""

    def __init__(self) -> None:
        self.priority_manager = PriorityManager()
        self.risk_assessor = RiskAssessor()
        self.replanner = OnlineReplanner()
        self._manual_override: Optional[Dict[str, Any]] = None
        self._active_override: Optional[Dict[str, Any]] = None
        self._last_decision: Dict[str, Any] = {}

    def force_override(
        self,
        action: str,
        source: str = "commander",
        reason: str = "commander_override",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._manual_override = {
            "action": str(action),
            "source": str(source),
            "reason": str(reason),
            "metadata": dict(metadata or {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return dict(self._manual_override)

    def cancel_override(self) -> bool:
        had_override = self._manual_override is not None or self._active_override is not None
        self._manual_override = None
        self._active_override = None
        return had_override

    def _inject_context_priorities(self, context: Dict[str, Any]) -> None:
        """Auto-inject survival/resource pressures into priority pool."""
        threat_distance = float(context.get("threat_distance", 999.0))
        battery_pct = float(context.get("battery_pct", 100.0))
        fuel_pct = float(context.get("fuel_pct", 100.0))
        comms_status = str(context.get("comms_status", "nominal")).lower()
        comms_quality = float(context.get("comms_quality", 1.0))
        if threat_distance < 30.0:
            self.priority_manager.add_priority(
                "auto_survival",
                base_priority=0.65,
                category="survival",
                escalation_rate=0.05,
                decay_rate=0.01,
                ttl_seconds=8.0,
            )
        if battery_pct < 25.0 or fuel_pct < 25.0:
            self.priority_manager.add_priority(
                "auto_resource",
                base_priority=0.60,
                category="resource",
                escalation_rate=0.04,
                decay_rate=0.01,
                ttl_seconds=10.0,
            )
        if comms_status in {"degraded", "lost"} or comms_quality < 0.35:
            self.priority_manager.add_priority(
                "auto_comms",
                base_priority=0.58,
                category="intel",
                escalation_rate=0.03,
                decay_rate=0.01,
                ttl_seconds=9.0,
            )

    def arbitrate(self, context: Dict[str, Any], current_action: Optional[str] = None) -> Dict[str, Any]:
        """Main tick pipeline: priority -> risk -> replan -> decision logic."""
        if not isinstance(context, dict):
            context = {}
        timestamp = context.get("timestamp")
        dt = 1.0
        if isinstance(timestamp, (int, float)) and isinstance(self._last_decision.get("timestamp"), (int, float)):
            dt = max(0.1, float(timestamp) - float(self._last_decision["timestamp"]))

        self._inject_context_priorities(context)
        self.priority_manager.tick(dt=dt)
        top_priority = self.priority_manager.top()

        risk_profile = self.risk_assessor.assess(context)
        risk_gate = str(risk_profile.get("decision_gate", "continue"))
        risk_trend = str(risk_profile.get("risk_trend", self.risk_assessor.trend()))

        replan = self.replanner.evaluate(context)
        replan_trigger = replan.trigger if replan is not None else None
        replan_directive = replan.action if replan is not None else None

        decision = {
            "override": False,
            "action": current_action or "continue",
            "reason": "continue",
            "risk_profile": risk_profile,
            "risk_trend": risk_trend,
            "replan_trigger": replan_trigger,
            "priority": asdict(top_priority) if top_priority else None,
            "manual_override": bool(self._manual_override),
            "timestamp": timestamp if isinstance(timestamp, (int, float)) else None,
        }

        if self._manual_override:
            decision["override"] = True
            decision["action"] = self._manual_override["action"]
            decision["reason"] = self._manual_override["reason"]
            decision["override_type"] = "manual"
            self._active_override = dict(decision)
            self._last_decision = dict(decision)
            return decision

        # Precedence: abort > replan > interrupt > reassess > continue.
        if risk_gate == "abort":
            decision["override"] = True
            decision["action"] = "abort_rtb"
            decision["reason"] = "risk_abort_gate"
            decision["override_type"] = "safety_abort"
        elif replan_directive:
            decision["override"] = True
            decision["action"] = replan_directive
            decision["reason"] = f"replan_{replan_trigger}"
            decision["override_type"] = "replan"
        elif top_priority and self.priority_manager.should_interrupt():
            decision["override"] = True
            decision["action"] = "interrupt"
            decision["reason"] = f"priority_interrupt:{top_priority['priority_id']}"
            decision["override_type"] = "priority_interrupt"
        elif risk_gate in {"replan", "escalate"}:
            decision["override"] = True
            decision["action"] = "hold_and_reassess"
            decision["reason"] = "risk_reassess_gate"
            decision["override_type"] = "reassess"

        # Decision reversal when conditions improve.
        if self._active_override and not self._manual_override:
            if risk_gate == "continue" and risk_trend in {"de-escalating", "de_escalating"}:
                decision["override"] = False
                decision["action"] = current_action or "continue"
                decision["reason"] = "conditions_improved_reversal"
                decision["override_reversal"] = True
                self._active_override = None

        if decision["override"]:
            self._active_override = dict(decision)

        # ROE hard guard.
        roe = str(context.get("rules_of_engagement", "weapons_hold")).lower()
        if roe == "weapons_hold" and str(decision.get("action", "")).lower() == "engage":
            decision["override"] = True
            decision["action"] = "hold"
            decision["reason"] = "roe_block_weapons_hold"
            decision["override_type"] = "roe_guard"

        self._last_decision = dict(decision)
        return decision

    def get_state(self) -> Dict[str, Any]:
        return {
            "manual_override": dict(self._manual_override) if self._manual_override else None,
            "active_override": dict(self._active_override) if self._active_override else None,
            "last_decision": dict(self._last_decision),
            "risk_trend": self.risk_assessor.trend(),
        }

    def list_priorities(self) -> list[Dict[str, Any]]:
        return self.priority_manager.active_priorities()

