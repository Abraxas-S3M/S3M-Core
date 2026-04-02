"""Data models for probabilistic tactical decision scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ActionType(str, Enum):
    """Supported tactical action classes."""

    ENGAGE = "ENGAGE"
    EVADE = "EVADE"
    HOLD = "HOLD"
    RECON = "RECON"
    RTB = "RTB"
    REPLAN = "REPLAN"
    ESCALATE = "ESCALATE"
    DEESCALATE = "DEESCALATE"
    SUPPORT = "SUPPORT"
    UNKNOWN = "UNKNOWN"


class ROELevel(str, Enum):
    """Rules-of-engagement posture."""

    WEAPONS_FREE = "WEAPONS_FREE"
    WEAPONS_TIGHT = "WEAPONS_TIGHT"
    WEAPONS_HOLD = "WEAPONS_HOLD"
    DEFENSIVE_ONLY = "DEFENSIVE_ONLY"
    NO_FORCE = "NO_FORCE"


class ROEConstraint(BaseModel):
    """ROE limits used to allow, block, or review options."""

    model_config = {"frozen": True}

    roe_level: ROELevel
    max_engagement_prob: float = Field(default=1.0, ge=0.0, le=1.0)
    require_human_review_above_risk: float = Field(default=0.8, ge=0.0, le=1.0)
    prohibited_action_types: List[ActionType] = Field(default_factory=list)
    notes: Optional[str] = None
    notes_ar: Optional[str] = None

    @classmethod
    def default(cls) -> "ROEConstraint":
        """Return the standard tactical default ROE constraint."""
        return cls(roe_level=ROELevel.WEAPONS_TIGHT)


class ObjectiveWeights(BaseModel):
    """Weights for multi-objective utility composition."""

    model_config = {"frozen": True}

    outcome_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    success_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    risk_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    cost_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    uncertainty_weight: float = Field(default=0.10, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "ObjectiveWeights":
        total = (
            self.outcome_weight
            + self.success_weight
            + self.risk_weight
            + self.cost_weight
            + self.uncertainty_weight
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError("Objective weights must sum to 1.0 ± 0.001")
        return self

    @classmethod
    def balanced(cls) -> "ObjectiveWeights":
        """Return an even weighting across all objectives."""
        return cls(
            outcome_weight=0.20,
            success_weight=0.20,
            risk_weight=0.20,
            cost_weight=0.20,
            uncertainty_weight=0.20,
        )

    @classmethod
    def risk_averse(cls) -> "ObjectiveWeights":
        """Return a weighting that penalizes risk more strongly."""
        return cls(
            outcome_weight=0.20,
            success_weight=0.20,
            risk_weight=0.35,
            cost_weight=0.10,
            uncertainty_weight=0.15,
        )

    @classmethod
    def mission_focused(cls) -> "ObjectiveWeights":
        """Return a weighting that emphasizes mission outcome."""
        return cls(
            outcome_weight=0.45,
            success_weight=0.30,
            risk_weight=0.10,
            cost_weight=0.05,
            uncertainty_weight=0.10,
        )


class DecisionOption(BaseModel):
    """One candidate action represented as normalized objective metrics."""

    model_config = {"frozen": True}

    option_id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    label_ar: Optional[str] = None
    action_type: ActionType = ActionType.UNKNOWN
    expected_outcome: float = Field(ge=0.0, le=1.0)
    probability_of_success: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    cost_score: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def _label_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label must not be blank")
        return stripped

    @property
    def raw_expected_value(self) -> float:
        """Return naive EV before objective penalties."""
        return self.probability_of_success * self.expected_outcome


class ScoredOption(BaseModel):
    """Decision option with computed utility and governance metadata."""

    model_config = {"frozen": True}

    option: DecisionOption
    utility_score: float
    ev_component: float
    risk_penalty: float
    cost_penalty: float
    uncertainty_penalty: float
    roe_vetoed: bool = False
    veto_reason: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    requires_human_review: bool = False
    rank: int = 0


class DecisionResult(BaseModel):
    """Output bundle for one scoring run."""

    model_config = {"frozen": True}

    result_id: str = Field(default_factory=lambda: str(uuid4()))
    selected: ScoredOption
    alternatives: List[ScoredOption]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    rationale_ar: str
    requires_human_review: bool
    belief_snapshot_id: Optional[str] = None
    scoring_breakdown: Dict[str, float]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def all_options(self) -> List[ScoredOption]:
        """Return selected and alternatives in rank order."""
        return sorted([self.selected, *self.alternatives], key=lambda item: item.rank)

    def was_vetoed(self, option_id: str) -> bool:
        """Return whether a given option was vetoed by ROE."""
        for scored in self.all_options():
            if scored.option.option_id == option_id:
                return scored.roe_vetoed
        return False


class ScoringContext(BaseModel):
    """Scoring context derived from doctrine posture and belief certainty."""

    model_config = {"frozen": True}

    weights: ObjectiveWeights
    roe: ROEConstraint
    belief_entropy: float = Field(default=0.0, ge=0.0)
    leading_hypothesis_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    mission_phase: str = "UNKNOWN"
    author_id: Optional[str] = None


class DecisionRecord(BaseModel):
    """Auditable record of one probabilistic decision computation."""

    model_config = {"frozen": True}

    record_id: str = Field(default_factory=lambda: str(uuid4()))
    result: DecisionResult
    context: ScoringContext
    options_evaluated: int
    options_vetoed: int
    computation_ms: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
