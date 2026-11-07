"""Council-to-gate planning step for Cortex evidence pipeline (Scenario B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.cortex.ace import ACEResult


@dataclass(frozen=True, slots=True)
class CortexPlan:
    plan_id: str
    case_id: str
    steps: List[Dict[str, Any]]
    proof_summary: str
    engine_versions: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "case_id": self.case_id,
            "steps": list(self.steps),
            "proof_summary": self.proof_summary,
            "engine_versions": dict(self.engine_versions),
        }


def build_plan(
    *,
    case_id: str,
    ace: Optional[ACEResult],
    council_output: str,
    engine_versions: Dict[str, str],
) -> CortexPlan:
    """Translate council / ACE output into gate-reviewable plan steps."""
    claims = []
    if ace is not None:
        claims = [c.text for c in ace.claims if c.accepted]
    steps = [
        {
            "kind": "analyze",
            "summary": council_output[:500],
            "accepted_claims": claims,
        },
        {
            "kind": "propose_change",
            "action": {
                "tool_name": "xiid.network_block",
                "autonomy_level": "bounded",
                "parameters": {"xiid_class": "C", "destination": "203.0.113.44"},
            },
        },
    ]
    proof = "ACE grounded claims" if ace is not None else "single-engine council output"
    return CortexPlan(
        plan_id=f"plan-{case_id[:8]}",
        case_id=case_id,
        steps=steps,
        proof_summary=proof,
        engine_versions=dict(engine_versions),
    )
