"""Escalation rule engine for correlated tactical threat handling."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.apps._shared import ensure_non_empty_text, utc_now_iso


class EscalationManager:
    """Deterministic and auditable escalation manager."""

    def __init__(self) -> None:
        self._rules: List[dict] = [
            {
                "name": "critical_immediate",
                "condition": "level == CRITICAL",
                "action": "alert_commander",
                "auto_response": False,
                "priority": 1,
            },
            {
                "name": "weapons_system_threat",
                "condition": "category == KINETIC and confidence > 0.8",
                "action": "alert_commander",
                "auto_response": False,
                "priority": 1,
            },
            {
                "name": "cyber_intrusion",
                "condition": "category == CYBER and level >= HIGH",
                "action": "isolate_segment",
                "auto_response": True,
                "priority": 2,
            },
            {
                "name": "swarm_detected",
                "condition": "pattern == swarm",
                "action": "scramble_interceptors",
                "auto_response": False,
                "priority": 1,
            },
            {
                "name": "hybrid_threat",
                "condition": "category == HYBRID",
                "action": "consensus_assessment",
                "auto_response": False,
                "priority": 1,
            },
        ]
        self._history: List[dict] = []
        self._active: Dict[str, dict] = {}

    @staticmethod
    def _level_rank(value: Any) -> int:
        mapping = {"INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
        return mapping.get(str(value).upper(), 0)

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value).strip().upper()

    def _split_and(self, condition: str) -> List[str]:
        tokens = [token.strip() for token in condition.split(" and ")]
        return [token for token in tokens if token]

    def _match_atom(self, atom: str, payload: dict) -> bool:
        if " >= " in atom:
            field, target = [part.strip() for part in atom.split(" >= ", 1)]
            current = payload.get(field)
            if field == "level":
                return self._level_rank(current) >= self._level_rank(target)
            try:
                return float(current) >= float(target)
            except (TypeError, ValueError):
                return False
        if " <= " in atom:
            field, target = [part.strip() for part in atom.split(" <= ", 1)]
            try:
                return float(payload.get(field)) <= float(target)
            except (TypeError, ValueError):
                return False
        if " > " in atom:
            field, target = [part.strip() for part in atom.split(" > ", 1)]
            try:
                return float(payload.get(field)) > float(target)
            except (TypeError, ValueError):
                return False
        if " < " in atom:
            field, target = [part.strip() for part in atom.split(" < ", 1)]
            try:
                return float(payload.get(field)) < float(target)
            except (TypeError, ValueError):
                return False
        if " == " in atom:
            field, target = [part.strip() for part in atom.split(" == ", 1)]
            return self._norm(payload.get(field)) == self._norm(target)
        return False

    def _match_condition(self, condition: str, payload: dict) -> bool:
        for atom in self._split_and(condition):
            if not self._match_atom(atom, payload):
                return False
        return True

    def evaluate(self, event_or_correlation: dict) -> Optional[dict]:
        """Evaluate one event/correlation against all rules."""
        if not isinstance(event_or_correlation, dict):
            raise ValueError("event_or_correlation must be a dictionary")
        matches: List[dict] = []
        for rule in self._rules:
            if self._match_condition(str(rule["condition"]), event_or_correlation):
                matches.append(rule)
        if not matches:
            return None
        selected = sorted(matches, key=lambda item: int(item["priority"]))[0]
        esc_id = str(uuid4())
        event_id = (
            event_or_correlation.get("event_id")
            or event_or_correlation.get("correlation_id")
            or event_or_correlation.get("id")
            or "unknown"
        )
        escalation = {
            "escalation_id": esc_id,
            "rule_name": selected["name"],
            "action": selected["action"],
            "auto_response": bool(selected["auto_response"]),
            "priority": int(selected["priority"]),
            "event_id": str(event_id),
            "timestamp": utc_now_iso(),
            "resolved": False,
            "resolution": None,
        }
        self._history.append(escalation)
        self._active[esc_id] = escalation
        return {
            "rule_name": escalation["rule_name"],
            "action": escalation["action"],
            "auto_response": escalation["auto_response"],
            "priority": escalation["priority"],
            "event_id": escalation["event_id"],
            "escalation_id": escalation["escalation_id"],
        }

    def evaluate_batch(self, events: List[dict]) -> List[dict]:
        """Evaluate a batch of events/correlations."""
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        out: List[dict] = []
        for event in events:
            triggered = self.evaluate(event)
            if triggered:
                out.append(triggered)
        return out

    def add_rule(
        self,
        name: str,
        condition: str,
        action: str,
        auto_response: bool = False,
        priority: int = 3,
    ) -> None:
        """Add escalation rule."""
        rule = {
            "name": ensure_non_empty_text(name, "name"),
            "condition": ensure_non_empty_text(condition, "condition"),
            "action": ensure_non_empty_text(action, "action"),
            "auto_response": bool(auto_response),
            "priority": int(priority),
        }
        self.remove_rule(rule["name"])
        self._rules.append(rule)
        self._rules.sort(key=lambda item: int(item["priority"]))

    def remove_rule(self, name: str) -> None:
        """Remove rule by name if present."""
        name = ensure_non_empty_text(name, "name")
        self._rules = [rule for rule in self._rules if rule["name"] != name]

    def get_rules(self) -> List[dict]:
        """Return configured escalation rules."""
        return [dict(rule) for rule in self._rules]

    def get_escalation_history(self, limit: int = 50) -> List[dict]:
        """Return historical triggered escalations."""
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        return self._history[-limit:]

    def get_active_escalations(self) -> List[dict]:
        """Return unresolved escalations."""
        return [dict(item) for item in self._active.values() if not item.get("resolved")]

    def resolve(self, escalation_id: str, resolution: str) -> None:
        """Mark escalation as resolved."""
        escalation_id = ensure_non_empty_text(escalation_id, "escalation_id")
        resolution = ensure_non_empty_text(resolution, "resolution")
        if escalation_id not in self._active:
            raise ValueError(f"Unknown escalation_id: {escalation_id}")
        self._active[escalation_id]["resolved"] = True
        self._active[escalation_id]["resolution"] = resolution
        self._active[escalation_id]["resolved_at"] = utc_now_iso()
