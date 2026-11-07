"""Mission Risk Catalog (MRC) snapshots for Cortex explainability.

Military/tactical context: commanders compare pre- and post-action risk posture
before approving brokered network mutations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class MRCSnapshot:
    score: float
    factors: Dict[str, float] = field(default_factory=dict)
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"score": float(self.score), "factors": dict(self.factors), "label": self.label}


def assess_mrc(*, evidence_count: int, ace_dropped: int, gate_allowed: bool) -> MRCSnapshot:
    """Heuristic MRC for cyber cases (offline, deterministic for tests)."""
    base = min(0.95, 0.25 + 0.08 * max(0, evidence_count))
    penalty = 0.05 * max(0, ace_dropped)
    if not gate_allowed:
        base += 0.1
    score = max(0.05, min(0.99, base - penalty))
    return MRCSnapshot(
        score=round(score, 4),
        factors={
            "evidence_coverage": float(evidence_count),
            "ace_dropped_claims": float(ace_dropped),
            "gate_blocked": 0.0 if gate_allowed else 1.0,
        },
        label="mrc_heuristic_v1",
    )
