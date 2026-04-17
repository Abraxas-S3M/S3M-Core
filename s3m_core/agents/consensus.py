"""Consensus and validation utilities for multi-subagent orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from .subagent import SubAgentResult
from .task_decomposer import SubTask

if TYPE_CHECKING:  # pragma: no cover
    from .subagent import SubAgent


@dataclass(slots=True)
class ValidationResult:
    """Validation decision for a single subagent result."""

    addresses_task: bool
    internally_consistent: bool
    conflicts_with_other_results: bool
    confidence_score: float
    rationale: str

    @property
    def accepted(self) -> bool:
        return (
            self.addresses_task
            and self.internally_consistent
            and not self.conflicts_with_other_results
            and self.confidence_score >= 0.6
        )


@dataclass(slots=True)
class ResolvedResult:
    """Conflict resolution outcome across multiple subagent results."""

    selected: Optional[SubAgentResult]
    ranking: List[Dict[str, Any]]
    rationale: str


@dataclass(slots=True)
class DebateResult:
    """Internal debate transcript and decision payload."""

    proposition: str
    rounds: int
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    winning_position: str = "undecided"
    rationale: str = ""


class MultiAgentConsensus:
    """
    Validate and reconcile outputs from multiple subagents.

    Tactical context:
    Consensus hardens mission reliability by forcing corroboration before the
    orchestrator accepts delegated outputs for command-level decisions.
    """

    def validate_result(
        self,
        result: SubAgentResult,
        validation_model: Any,
        original_task: SubTask,
    ) -> ValidationResult:
        model_decision = self._validate_with_model(result, validation_model, original_task)
        if model_decision is not None:
            return model_decision

        description_tokens = {
            token for token in original_task.description.lower().split() if len(token) > 2
        }
        output_text = str(result.output).lower()
        overlap = sum(1 for token in description_tokens if token in output_text)
        addresses_task = overlap > 0 or result.success
        internally_consistent = result.success and bool(result.output)
        conflicts = bool(result.output.get("conflicts")) if isinstance(result.output, dict) else False
        confidence = 0.25 + (0.35 if addresses_task else 0.0) + (0.30 if internally_consistent else 0.0)
        if conflicts:
            confidence -= 0.3
        confidence = max(0.0, min(confidence, 1.0))
        rationale = (
            f"Token overlap={overlap}, success={result.success}, conflicts={conflicts}, "
            f"confidence={confidence:.2f}"
        )
        return ValidationResult(
            addresses_task=addresses_task,
            internally_consistent=internally_consistent,
            conflicts_with_other_results=conflicts,
            confidence_score=confidence,
            rationale=rationale,
        )

    def resolve_conflicts(self, results: List[SubAgentResult]) -> ResolvedResult:
        if not results:
            return ResolvedResult(selected=None, ranking=[], rationale="No subagent results provided")

        vote_counts: Dict[str, int] = {}
        confidence_weight: Dict[str, float] = {}
        result_lookup: Dict[str, SubAgentResult] = {}
        for item in results:
            signature = self._result_signature(item)
            vote_counts[signature] = vote_counts.get(signature, 0) + 1
            confidence_weight[signature] = confidence_weight.get(signature, 0.0) + self._confidence_hint(item)
            result_lookup.setdefault(signature, item)

        ranking = sorted(
            (
                {
                    "signature": signature,
                    "votes": votes,
                    "weighted_confidence": confidence_weight[signature],
                }
                for signature, votes in vote_counts.items()
            ),
            key=lambda item: (item["votes"], item["weighted_confidence"]),
            reverse=True,
        )
        winner_sig = ranking[0]["signature"]
        selected = result_lookup[winner_sig]
        rationale = (
            "Resolved by majority voting with confidence weighting; "
            f"winner votes={ranking[0]['votes']} weighted_confidence={ranking[0]['weighted_confidence']:.2f}"
        )
        return ResolvedResult(selected=selected, ranking=ranking, rationale=rationale)

    def debate(self, proposition: str, agents: Sequence["SubAgent"], rounds: int = 3) -> DebateResult:
        transcript: List[Dict[str, Any]] = []
        support_score = 0.0
        oppose_score = 0.0
        prior_arguments: List[str] = []
        for round_idx in range(rounds):
            for agent_idx, agent in enumerate(agents):
                stance = "support" if agent_idx % 2 == 0 else "oppose"
                argument = self._collect_argument(
                    agent=agent,
                    proposition=proposition,
                    prior_arguments=prior_arguments,
                    stance=stance,
                )
                quality = max(min(len(argument) / 180.0, 1.0), 0.1)
                if stance == "support":
                    support_score += quality
                else:
                    oppose_score += quality
                prior_arguments.append(argument)
                transcript.append(
                    {
                        "round": round_idx + 1,
                        "agent_id": getattr(agent, "agent_id", f"agent-{agent_idx + 1}"),
                        "stance": stance,
                        "argument": argument,
                        "quality": round(quality, 3),
                    }
                )
        winning_position = "support" if support_score >= oppose_score else "oppose"
        rationale = (
            f"Support score={support_score:.2f}, oppose score={oppose_score:.2f}; "
            "decision selected by argument quality aggregate."
        )
        return DebateResult(
            proposition=proposition,
            rounds=rounds,
            transcript=transcript,
            winning_position=winning_position,
            rationale=rationale,
        )

    def _validate_with_model(
        self,
        result: SubAgentResult,
        validation_model: Any,
        original_task: SubTask,
    ) -> Optional[ValidationResult]:
        if validation_model is None:
            return None
        validator = getattr(validation_model, "validate_result", None)
        if callable(validator):
            decision = validator(result=result, task=original_task)
            if isinstance(decision, dict):
                return ValidationResult(
                    addresses_task=bool(decision.get("addresses_task", False)),
                    internally_consistent=bool(decision.get("internally_consistent", False)),
                    conflicts_with_other_results=bool(decision.get("conflicts", False)),
                    confidence_score=float(decision.get("confidence_score", 0.0)),
                    rationale=str(decision.get("rationale", "validated by model")),
                )
        return None

    @staticmethod
    def _collect_argument(
        *,
        agent: "SubAgent",
        proposition: str,
        prior_arguments: List[str],
        stance: str,
    ) -> str:
        method = getattr(agent, "build_argument", None)
        if callable(method):
            try:
                return str(method(proposition, prior_arguments=prior_arguments, stance=stance))
            except Exception:
                pass
        task_text = getattr(getattr(agent, "task", None), "description", "mission task")
        return (
            f"{stance.upper()} argument for '{proposition}': "
            f"subagent focus '{task_text}'. Prior points considered={len(prior_arguments)}."
        )

    @staticmethod
    def _result_signature(result: SubAgentResult) -> str:
        if isinstance(result.output, dict):
            if "task_description" in result.output:
                return str(result.output["task_description"]).strip().lower()
            return str(sorted(result.output.items()))
        return str(result.output)

    @staticmethod
    def _confidence_hint(result: SubAgentResult) -> float:
        if isinstance(result.output, dict):
            raw = result.output.get("confidence")
            if isinstance(raw, (int, float)):
                return float(raw)
        return 0.7 if result.success else 0.2
