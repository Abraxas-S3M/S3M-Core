"""Mission command engine for tactical order generation.

This wrapper keeps command-and-control orchestration lightweight so it can run
offline on edge hardware without requiring model weight preloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.llm_core import Orchestrator, TaskDomain


@dataclass(frozen=True)
class CommandDecision:
    """Structured command decision for audit-safe mission execution."""

    action: str
    recommendation_text: str
    confidence: float
    review_required: bool


class MissionCommandEngine:
    """Generate command recommendations with strict payload validation."""

    def __init__(self, orchestrator: Optional[Orchestrator] = None) -> None:
        self._orchestrator = orchestrator or Orchestrator()

    @staticmethod
    def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")
        mission_brief = str(payload.get("mission_brief", "")).strip()
        if not mission_brief:
            raise ValueError("mission_brief must be a non-empty string")
        requested_action = str(payload.get("requested_action", "ASSESS")).strip().upper()
        return {
            "mission_brief": mission_brief,
            "requested_action": requested_action,
            "domain": str(payload.get("domain", "tactical")).strip().lower(),
        }

    @staticmethod
    def _resolve_domain(domain: str) -> TaskDomain:
        mapping = {
            "tactical": TaskDomain.TACTICAL,
            "planning": TaskDomain.PLANNING,
            "reasoning": TaskDomain.REASONING,
            "arabic_nlp": TaskDomain.ARABIC_NLP,
        }
        return mapping.get(domain, TaskDomain.TACTICAL)

    def evaluate(self, payload: Dict[str, Any]) -> CommandDecision:
        data = self._validate_payload(payload)
        # Tactical context: route command authority through doctrine-aware orchestrator.
        routed = self._orchestrator.route_and_decide(
            prompt=data["mission_brief"],
            domain=self._resolve_domain(data["domain"]),
            require_consensus=False,
            metadata={"requested_action": data["requested_action"]},
        )
        confidence_map = routed.get("confidence_scores", {})
        confidence = 0.0
        if isinstance(confidence_map, dict) and confidence_map:
            confidence = float(max(confidence_map.values()))
        return CommandDecision(
            action=data["requested_action"],
            recommendation_text=str(routed.get("recommendation_text", "")),
            confidence=max(0.0, min(1.0, confidence)),
            review_required=bool(routed.get("review_required", True)),
        )

    def issue_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility wrapper returning a dictionary payload for API routes."""
        decision = self.evaluate(payload)
        return {
            "action": decision.action,
            "recommendation_text": decision.recommendation_text,
            "confidence": decision.confidence,
            "review_required": decision.review_required,
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "component": "mission_command_engine",
            "offline_mode": True,
        }
