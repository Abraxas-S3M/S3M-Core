"""PCCP change request wrapping (propose-only; execution via broker).

Military/tactical context: every proposed network change carries explicit
invariants so rollback stays bounded if the tactical network must recover quickly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from src.cortex.reachability import MRCAction, MRCPlan


@dataclass
class ChangeInvariant:
    name: str
    description: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeStep:
    step_id: str
    edge_id: str
    action: str
    cost: float
    disruption: float
    expected_risk_after: float


@dataclass
class ChangeRequest:
    case_id: str
    created_at: str
    target_risk: float
    budget: float
    steps: List[ChangeStep]
    invariants: List[ChangeInvariant]
    rationale: Dict[str, Any]
    initial_risk: float
    projected_final_risk: float
    status: str = "proposed"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> ChangeRequest:
        steps = [ChangeStep(**s) for s in payload.get("steps", [])]
        invariants = [ChangeInvariant(**i) for i in payload.get("invariants", [])]
        return cls(
            case_id=str(payload["case_id"]),
            created_at=str(payload["created_at"]),
            target_risk=float(payload["target_risk"]),
            budget=float(payload["budget"]),
            steps=steps,
            invariants=invariants,
            rationale=dict(payload.get("rationale", {})),
            initial_risk=float(payload["initial_risk"]),
            projected_final_risk=float(payload["projected_final_risk"]),
            status=str(payload.get("status", "proposed")),
        )

    @classmethod
    def from_json(cls, text: str) -> ChangeRequest:
        return cls.from_dict(json.loads(text))


def standard_invariants(max_blast_radius: int) -> List[ChangeInvariant]:
    return [
        ChangeInvariant(
            name="max_blast_radius",
            description="No single change step may touch more than max_blast_radius nodes.",
            params={"max_blast_radius": int(max_blast_radius)},
        ),
        ChangeInvariant(
            name="required_flows",
            description="All mission-required flows must remain reachable after each step.",
            params={},
        ),
        ChangeInvariant(
            name="reversible",
            description="Each step must be reversible via broker rollback metadata.",
            params={},
        ),
    ]


def build_change(
    case_id: str,
    plan: MRCPlan,
    *,
    target_risk: float,
    budget: float,
    rationale: Dict[str, Any],
    max_blast_radius: int,
) -> ChangeRequest:
    steps: List[ChangeStep] = []
    for idx, act in enumerate(plan.actions):
        steps.append(
            ChangeStep(
                step_id=f"{case_id}-step-{idx + 1}",
                edge_id=act.edge_id,
                action=act.action,
                cost=act.cost,
                disruption=act.disruption,
                expected_risk_after=act.risk_after,
            )
        )

    invariants = standard_invariants(max_blast_radius)
    for step in steps:
        touched = 2
        if touched > max_blast_radius:
            raise ValueError(f"Step {step.step_id} exceeds max_blast_radius invariant")

    return ChangeRequest(
        case_id=case_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        target_risk=float(target_risk),
        budget=float(budget),
        steps=steps,
        invariants=invariants,
        rationale=rationale,
        initial_risk=plan.initial_risk,
        projected_final_risk=plan.final_risk,
        status="proposed",
    )


def execute_change(change: ChangeRequest) -> None:
    """Execution is intentionally not supported in the planner layer."""
    raise NotImplementedError(
        "Change execution is broker-only (Prompt 12). Planner proposes ChangeRequest JSON only."
    )
