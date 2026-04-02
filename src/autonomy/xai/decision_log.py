"""Decision logging for tactical autonomy explainability.

Maintains an auditable FIFO store of autonomous decisions for command review,
assurance workflows, and after-action analysis in military operations.
"""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from typing import Deque, Dict, List, Optional

from src.autonomy.models import AutonomyDecision


class DecisionLog:
    """FIFO-backed decision archive with query and export support."""

    def __init__(self, max_entries: int = 50000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self.max_entries = int(max_entries)
        self._entries: Deque[AutonomyDecision] = deque(maxlen=self.max_entries)

    def log(self, decision: AutonomyDecision) -> None:
        """Append decision entry with automatic rotation at capacity."""
        if not isinstance(decision, AutonomyDecision):
            raise TypeError("decision must be an AutonomyDecision")
        self._entries.append(decision)

    def get(self, decision_id: str) -> Optional[AutonomyDecision]:
        """Return decision by ID if present."""
        for decision in reversed(self._entries):
            if decision.decision_id == decision_id:
                return decision
        return None

    def query(
        self,
        agent_id: Optional[str] = None,
        decision_type: Optional[str] = None,
        mission_id: Optional[str] = None,
        requires_review: Optional[bool] = None,
        limit: int = 50,
    ) -> List[AutonomyDecision]:
        """Query decisions with tactical filter criteria."""
        normalized_type = decision_type.lower() if decision_type else None
        results: List[AutonomyDecision] = []
        for decision in reversed(self._entries):
            if agent_id and decision.agent_id != agent_id:
                continue
            if normalized_type and decision.decision_type.value != normalized_type:
                continue
            if mission_id and decision.mission_id != mission_id:
                continue
            if requires_review is not None and decision.requires_human_review != bool(requires_review):
                continue
            results.append(decision)
            if len(results) >= max(1, limit):
                break
        return results

    def get_stats(self) -> Dict[str, object]:
        """Compute aggregate decision statistics for mission assurance dashboards."""
        total = len(self._entries)
        by_type: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        review_pending = 0
        confidence_sum = 0.0
        for decision in self._entries:
            by_type[decision.decision_type.value] = by_type.get(decision.decision_type.value, 0) + 1
            by_agent[decision.agent_id] = by_agent.get(decision.agent_id, 0) + 1
            if decision.requires_human_review:
                review_pending += 1
            confidence_sum += decision.confidence
        avg_confidence = confidence_sum / total if total else 0.0
        return {
            "total_decisions": total,
            "by_type": by_type,
            "by_agent": by_agent,
            "review_pending": review_pending,
            "avg_confidence": avg_confidence,
        }

    def export(self, filepath: str) -> None:
        """Export log to JSON file for secure mission archival."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for decision in self._entries:
            entry = decision.to_dict()
            # Tactical audit extension fields for realtime override analysis.
            context = decision.context if isinstance(decision.context, dict) else {}
            entry["arbiter_override"] = bool(context.get("arbiter_override", False))
            entry["risk_profile"] = dict(context.get("risk_profile", {})) if isinstance(context.get("risk_profile"), dict) else {}
            entry["replan_trigger"] = context.get("replan_trigger")
            payload.append(entry)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        """Clear all entries from log."""
        self._entries.clear()

