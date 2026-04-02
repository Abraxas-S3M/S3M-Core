"""
Structured reconciliation engine for S3M unified runtime.

This module replaces text-only consensus with state-aware conflict handling that
uses confidence, domain specialization, trust weighting, and ROE constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from .engine_output import ActionCandidate, EngineHealth, StructuredEngineOutput, ThreatEntity
from .shared_state import DecisionRecord, MissionState


class ConflictResolutionStrategy(str, Enum):
    """Conflict resolution strategies used by structured reconciliation."""

    HIGHER_CONFIDENCE_WINS = "HIGHER_CONFIDENCE_WINS"
    DOMAIN_SPECIALIST_WINS = "DOMAIN_SPECIALIST_WINS"
    WEIGHTED_MERGE = "WEIGHTED_MERGE"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    ROE_DEFENSIVE_PREFERENCE = "ROE_DEFENSIVE_PREFERENCE"


@dataclass(slots=True)
class ReconciliationSummary:
    """Summary report for reconciliation telemetry and mission audit."""

    healthy_outputs: int
    unhealthy_outputs: int
    conflicts_detected: int
    conflicts_resolved: int
    escalations: int
    selected_threat: Optional[str] = None
    selected_action: Optional[str] = None
    applied_strategies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable summary."""
        return {
            "healthy_outputs": self.healthy_outputs,
            "unhealthy_outputs": self.unhealthy_outputs,
            "conflicts_detected": self.conflicts_detected,
            "conflicts_resolved": self.conflicts_resolved,
            "escalations": self.escalations,
            "selected_threat": self.selected_threat,
            "selected_action": self.selected_action,
            "applied_strategies": list(self.applied_strategies),
        }


class ReconciliationEngine:
    """
    Structured state reconciliation pipeline.

    Pipeline:
      1) filter unhealthy outputs
      2) ingest all outputs into state
      3) detect conflicts
      4) resolve conflicts
      5) reconcile threats
      6) reconcile actions
      7) synthesize authoritative decision
    """

    def reconcile(
        self,
        outputs: Dict[Any, StructuredEngineOutput],
        state: MissionState,
        *,
        ingest_outputs: bool = True,
    ) -> DecisionRecord:
        """Reconcile structured outputs into one authoritative decision."""
        all_outputs = list(outputs.values())
        healthy = [item for item in all_outputs if item.health == EngineHealth.HEALTHY]
        unhealthy = [item for item in all_outputs if item.health != EngineHealth.HEALTHY]

        if ingest_outputs:
            # Tactical context: ingest every output for full provenance and audit,
            # even degraded ones, while only healthy outputs influence confidence.
            for output in all_outputs:
                state.ingest_engine_output(output)

        pending = state.get_conflicts(pending_only=True)
        applied_strategies: List[str] = []
        escalations = 0
        resolved = 0
        for conflict in pending:
            strategy, value, escalate = self._resolve_conflict(state=state, conflict=conflict.to_dict())
            record = state.resolve_conflict(
                conflict.conflict_id,
                strategy=strategy.value,
                resolved_value=value,
                requires_human_review=escalate,
            )
            if record is not None:
                resolved += 1
                applied_strategies.append(strategy.value)
                if escalate:
                    escalations += 1

        selected_threat = self._reconcile_threats(state.get_authoritative_threats(), state)
        selected_action = self._reconcile_actions(
            actions=state.get_authoritative_actions(),
            rules_of_engagement=state.snapshot().get("context", {}).get("rules_of_engagement", "weapons_hold"),
        )

        agreement_bonus = self._agreement_bonus(healthy)
        base_confidence = self._base_confidence(healthy)
        final_confidence = max(0.0, min(1.0, base_confidence + agreement_bonus))
        review_status = self._review_status(
            confidence=final_confidence,
            escalations=escalations,
            healthy_count=len(healthy),
        )

        rationale = [
            f"Healthy engines: {len(healthy)}",
            f"Unhealthy engines: {len(unhealthy)}",
            f"Conflicts resolved: {resolved}",
            f"Agreement bonus: {agreement_bonus:.3f}",
        ]
        if selected_threat:
            rationale.append(f"Primary threat: {selected_threat}")
        if selected_action:
            rationale.append(f"Primary action: {selected_action}")
        if escalations:
            rationale.append("ROE escalation required for one or more action conflicts.")

        context = state.snapshot().get("context", {})
        mission_id = str(context.get("mission_id", ""))
        decision_text = self._compose_decision_text(
            selected_threat=selected_threat,
            selected_action=selected_action,
            review_status=review_status,
        )
        decision = DecisionRecord(
            decision_id=str(uuid4()),
            mission_id=mission_id,
            decision_text=decision_text,
            confidence=final_confidence,
            review_status=review_status,
            selected_action=selected_action,
            selected_threat=selected_threat,
            provenance_engines=sorted({item.engine_id for item in healthy}),
            rationale=rationale,
        )
        state.add_decision(decision)
        return decision

    def _resolve_conflict(
        self,
        *,
        state: MissionState,
        conflict: Dict[str, Any],
    ) -> tuple[ConflictResolutionStrategy, Any, bool]:
        """Resolve one conflict record using strategy policy and ROE context."""
        field_path = str(conflict.get("field_path", ""))
        existing_engine = str(conflict.get("existing_engine", ""))
        incoming_engine = str(conflict.get("incoming_engine", ""))
        existing_conf = float(conflict.get("existing_confidence", 0.0))
        incoming_conf = float(conflict.get("incoming_confidence", 0.0))
        existing_value = conflict.get("existing_value")
        incoming_value = conflict.get("incoming_value")
        rules = state.snapshot().get("context", {}).get("rules_of_engagement", "weapons_hold")

        # Tactical context: offensive actions under restrictive ROE are escalated
        # to prevent autonomous escalation during ambiguous engagements.
        if field_path.startswith("actions.") and rules == "weapons_tight":
            action_tokens = f"{existing_value} {incoming_value}".lower()
            if any(token in action_tokens for token in ("engage", "attack", "strike", "assault")):
                return ConflictResolutionStrategy.ESCALATE_TO_HUMAN, existing_value, True

        if field_path.startswith("actions.") and rules == "weapons_hold":
            existing_def = self._is_defensive_action(existing_value)
            incoming_def = self._is_defensive_action(incoming_value)
            if existing_def and not incoming_def:
                return (
                    ConflictResolutionStrategy.ROE_DEFENSIVE_PREFERENCE,
                    existing_value,
                    False,
                )
            if incoming_def and not existing_def:
                return (
                    ConflictResolutionStrategy.ROE_DEFENSIVE_PREFERENCE,
                    incoming_value,
                    False,
                )

        if field_path.startswith("threats."):
            specialist = state.get_domain_specialist("threat")
            if specialist and (incoming_engine == specialist or existing_engine == specialist):
                winner = incoming_value if incoming_engine == specialist else existing_value
                return ConflictResolutionStrategy.DOMAIN_SPECIALIST_WINS, winner, False

        if isinstance(existing_value, (int, float)) and isinstance(incoming_value, (int, float)):
            ew = max(0.0, min(1.0, state.get_engine_trust(existing_engine)))
            iw = max(0.0, min(1.0, state.get_engine_trust(incoming_engine)))
            denominator = (ew * existing_conf) + (iw * incoming_conf)
            if denominator <= 0:
                merged = float(existing_value + incoming_value) / 2.0
            else:
                merged = (
                    (float(existing_value) * ew * existing_conf)
                    + (float(incoming_value) * iw * incoming_conf)
                ) / denominator
            return ConflictResolutionStrategy.WEIGHTED_MERGE, merged, False

        if incoming_conf >= existing_conf:
            return ConflictResolutionStrategy.HIGHER_CONFIDENCE_WINS, incoming_value, False
        return ConflictResolutionStrategy.HIGHER_CONFIDENCE_WINS, existing_value, False

    @staticmethod
    def _is_defensive_action(value: Any) -> bool:
        """Return True when a value string indicates defensive behavior."""
        lowered = str(value or "").lower()
        return any(token in lowered for token in ("hold", "defend", "secure", "monitor", "observe", "contain"))

    @staticmethod
    def _reconcile_threats(threats: Iterable[ThreatEntity], state: MissionState) -> Optional[str]:
        """Select authoritative threat label from ranked threat entities."""
        ranked = sorted(
            list(threats),
            key=lambda item: (
                item.confidence * state.get_engine_trust(item.provenance_engine or ""),
                item.severity == "high",
            ),
            reverse=True,
        )
        if not ranked:
            return None
        return ranked[0].label

    @staticmethod
    def _reconcile_actions(
        *,
        actions: Iterable[ActionCandidate],
        rules_of_engagement: str,
    ) -> Optional[str]:
        """Select authoritative action candidate with ROE-aware ordering."""
        ranked = list(actions)
        if not ranked:
            return None

        if rules_of_engagement == "weapons_hold":
            ranked.sort(
                key=lambda action: (
                    action.action_type == "defensive",
                    action.confidence,
                    -action.priority,
                ),
                reverse=True,
            )
            return ranked[0].action

        if rules_of_engagement == "weapons_tight":
            ranked.sort(
                key=lambda action: (
                    action.action_type != "offensive",
                    action.confidence,
                    -action.priority,
                ),
                reverse=True,
            )
            return ranked[0].action

        ranked.sort(key=lambda action: (action.confidence, -action.priority), reverse=True)
        return ranked[0].action

    @staticmethod
    def _base_confidence(outputs: List[StructuredEngineOutput]) -> float:
        """Return mean confidence of healthy outputs."""
        if not outputs:
            return 0.0
        return sum(item.confidence for item in outputs) / len(outputs)

    @staticmethod
    def _agreement_bonus(outputs: List[StructuredEngineOutput]) -> float:
        """
        Compute confidence bonus when engines agree on key artifacts.

        Tactical context:
        - Agreement bonus slightly boosts confidence when top actions/threats
          converge across engines, but never overwhelms base confidence.
        """
        if len(outputs) < 2:
            return 0.0

        action_votes: Dict[str, int] = {}
        threat_votes: Dict[str, int] = {}
        for output in outputs:
            if output.actions:
                key = output.actions[0].action.lower()
                action_votes[key] = action_votes.get(key, 0) + 1
            if output.threats:
                key = output.threats[0].label.lower()
                threat_votes[key] = threat_votes.get(key, 0) + 1

        consensus_ratio = 0.0
        if action_votes:
            consensus_ratio += max(action_votes.values()) / len(outputs)
        if threat_votes:
            consensus_ratio += max(threat_votes.values()) / len(outputs)

        if action_votes and threat_votes:
            consensus_ratio /= 2.0
        return min(0.12, max(0.0, consensus_ratio * 0.12))

    @staticmethod
    def _review_status(*, confidence: float, escalations: int, healthy_count: int) -> str:
        """Determine ACCEPT/REVIEW/REJECT gate from confidence and escalation."""
        if healthy_count == 0:
            return "REJECT"
        if escalations > 0:
            return "REVIEW"
        if confidence >= 0.78:
            return "ACCEPT"
        if confidence >= 0.45:
            return "REVIEW"
        return "REJECT"

    @staticmethod
    def _compose_decision_text(
        *,
        selected_threat: Optional[str],
        selected_action: Optional[str],
        review_status: str,
    ) -> str:
        """Compose concise mission decision text for downstream consumers."""
        threat_txt = selected_threat or "no dominant threat identified"
        action_txt = selected_action or "maintain observation posture"
        return (
            f"Authoritative decision: prioritize {action_txt}. "
            f"Primary threat assessment: {threat_txt}. "
            f"Review posture: {review_status}."
        )
