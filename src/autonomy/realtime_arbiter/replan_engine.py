"""Online replanning triggers and directive generation for tick arbitration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import time


TRIGGERS = (
    "threat_detected",
    "threat_escalation",
    "resource_bingo",
    "new_orders",
    "comms_degraded",
    "comms_lost",
    "mission_window_closing",
    "belief_shift",
    "agent_lost",
    "mission_blocked",
)


@dataclass
class ReplanDirective:
    action: str
    trigger: str
    rationale: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class OnlineReplanner:
    """Evaluates replanning triggers and emits tactical directives."""

    def __init__(self, cooldown_seconds: float = 5.0) -> None:
        self.cooldown_seconds = max(0.1, float(cooldown_seconds))
        self._last_trigger_time: Dict[str, float] = {}
        self._evaluators: Dict[str, Callable[[Dict[str, Any]], bool]] = {}

    def register_evaluator(self, trigger: str, evaluator: Callable[[Dict[str, Any]], bool]) -> None:
        if trigger not in TRIGGERS:
            raise ValueError(f"unknown trigger: {trigger}")
        self._evaluators[trigger] = evaluator

    def _in_cooldown(self, trigger: str, now: float) -> bool:
        last = self._last_trigger_time.get(trigger)
        if last is None:
            return False
        return (now - last) < self.cooldown_seconds

    def _evaluate_trigger(self, trigger: str, context: Dict[str, Any]) -> bool:
        custom = self._evaluators.get(trigger)
        if custom is not None:
            try:
                return bool(custom(context))
            except Exception:
                return False

        if trigger == "threat_detected":
            return bool(context.get("threat_detected")) or float(context.get("threat_level", 0.0)) > 0.6
        if trigger == "threat_escalation":
            return str(context.get("risk_trend", "stable")) == "escalating"
        if trigger == "resource_bingo":
            return (
                float(context.get("fuel_pct", 100.0)) < 20.0
                or float(context.get("battery_pct", 100.0)) < 20.0
            )
        if trigger == "new_orders":
            return bool(context.get("new_orders"))
        if trigger == "comms_degraded":
            return str(context.get("comms_status", "nominal")) == "degraded"
        if trigger == "comms_lost":
            return str(context.get("comms_status", "nominal")) == "lost"
        if trigger == "mission_window_closing":
            return float(context.get("mission_time_remaining_s", 9999.0)) < 60.0
        if trigger == "belief_shift":
            return float(context.get("belief_shift", 0.0)) > 0.4
        if trigger == "agent_lost":
            return bool(context.get("agent_lost"))
        if trigger == "mission_blocked":
            return bool(context.get("mission_blocked"))
        return False

    def _directive_for_trigger(self, trigger: str) -> ReplanDirective:
        mapping = {
            "threat_detected": ("reroute", "Threat contact detected; route around hostile axis."),
            "threat_escalation": ("pivot_mission", "Escalating threat trend requires mission pivot."),
            "resource_bingo": ("abort_rtb", "Resource bingo reached; return to base for survival."),
            "new_orders": ("pivot_mission", "Higher command issued new orders."),
            "comms_degraded": ("hold_and_reassess", "Comms degraded; hold while preserving link integrity."),
            "comms_lost": ("escalate", "Comms lost; escalate to command authority fallback."),
            "mission_window_closing": ("add_subtask", "Mission window closing; add urgency subtask."),
            "belief_shift": ("replan", "Belief state shifted materially; re-evaluate plan."),
            "agent_lost": ("add_subtask", "Agent loss detected; reassign responsibilities."),
            "mission_blocked": ("hold_and_reassess", "Mission blocked by constraints; reassess options."),
        }
        action, rationale = mapping.get(trigger, ("continue", "No replanning required."))
        return ReplanDirective(action=action, trigger=trigger, rationale=rationale, metadata={})

    def evaluate(self, context: Dict[str, Any], now: Optional[float] = None) -> Optional[ReplanDirective]:
        """Return highest-priority trigger directive if one fires."""
        timestamp = float(time.time() if now is None else now)
        for trigger in TRIGGERS:
            if self._in_cooldown(trigger, timestamp):
                continue
            if self._evaluate_trigger(trigger, context):
                self._last_trigger_time[trigger] = timestamp
                return self._directive_for_trigger(trigger)
        return None

