"""Data models for multi-factor tactical risk assessment.

Military context:
These structures standardize probabilistic loss estimates used by commanders to
accept, mitigate, or abort operations before force and asset losses occur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    """Risk severity classification for command decision support."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    BLACK = "black"


class RiskCategory(Enum):
    """Risk dimensions considered by the Bayesian risk network."""

    EQUIPMENT_LOSS = "equipment_loss"
    PERSONNEL_CASUALTY = "personnel_casualty"
    MISSION_FAILURE = "mission_failure"
    COLLATERAL_DAMAGE = "collateral_damage"
    STRATEGIC_IMPACT = "strategic_impact"


@dataclass
class RiskFactor:
    """Single evidence factor contributing to mission risk computation."""

    factor_id: str
    name: str
    category: RiskCategory
    weight: float
    score: float
    confidence: float
    source: str
    detail: str
    mitigations: List[str]


@dataclass
class RiskAssessment:
    """Comprehensive risk assessment output for mission authorization workflows."""

    assessment_id: str
    context: str
    timestamp: datetime
    equipment_loss_prob: float
    personnel_casualty_prob: float
    mission_failure_prob: float
    cost_estimate_usd: float
    risk_level: RiskLevel
    risk_factors: List[RiskFactor]
    overall_score: float
    interaction_effects: List[dict]
    recommendation_en: str
    recommendation_ar: str
    llm_analysis: Optional[str]
    approved_by: Optional[str]
    xai_explanation: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize risk assessment for dashboards and audit records."""
        return {
            "assessment_id": self.assessment_id,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "equipment_loss_prob": self.equipment_loss_prob,
            "personnel_casualty_prob": self.personnel_casualty_prob,
            "mission_failure_prob": self.mission_failure_prob,
            "cost_estimate_usd": self.cost_estimate_usd,
            "risk_level": self.risk_level.value,
            "risk_factors": [
                {
                    "factor_id": f.factor_id,
                    "name": f.name,
                    "category": f.category.value,
                    "weight": f.weight,
                    "score": f.score,
                    "confidence": f.confidence,
                    "source": f.source,
                    "detail": f.detail,
                    "mitigations": list(f.mitigations),
                }
                for f in self.risk_factors
            ],
            "overall_score": self.overall_score,
            "interaction_effects": list(self.interaction_effects),
            "recommendation_en": self.recommendation_en,
            "recommendation_ar": self.recommendation_ar,
            "llm_analysis": self.llm_analysis,
            "approved_by": self.approved_by,
            "xai_explanation": self.xai_explanation,
        }

    def is_acceptable(self, max_level: RiskLevel = RiskLevel.AMBER) -> bool:
        """Check if risk level is within acceptable command threshold."""
        order = {
            RiskLevel.GREEN: 1,
            RiskLevel.AMBER: 2,
            RiskLevel.RED: 3,
            RiskLevel.BLACK: 4,
        }
        return order[self.risk_level] <= order[max_level]

    def top_risk_factors(self, n=3) -> List[RiskFactor]:
        """Return top contributing risk factors by weighted contribution."""
        ranked = sorted(self.risk_factors, key=lambda f: f.weight * f.score, reverse=True)
        return ranked[: max(1, int(n))]


@dataclass
class RiskProfile:
    """Historical risk exposure profile for units or assets."""

    entity_id: str
    entity_type: str
    risk_history: List[dict] = field(default_factory=list)
    cumulative_risk_exposure: float = 0.0
    incidents: List[dict] = field(default_factory=list)
