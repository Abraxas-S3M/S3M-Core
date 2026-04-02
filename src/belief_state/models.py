"""Core data models for the S3M belief-state runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class HypothesisStatus(str, Enum):
    """Lifecycle status for a belief hypothesis."""

    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"


class DoctrineType(str, Enum):
    """Operational doctrine categories for mission context."""

    PEACE_SUPPORT = "PEACE_SUPPORT"
    COUNTER_TERROR = "COUNTER_TERROR"
    CONVENTIONAL = "CONVENTIONAL"
    ASYMMETRIC = "ASYMMETRIC"
    MARITIME = "MARITIME"
    CYBER_DEFENCE = "CYBER_DEFENCE"
    UNKNOWN = "UNKNOWN"


class EvidenceLayer(str, Enum):
    """Source layer of evidence in the S3M stack."""

    LAYER_01_LLM = "LAYER_01_LLM"
    LAYER_02_THREAT = "LAYER_02_THREAT"
    LAYER_03_AUTONOMY = "LAYER_03_AUTONOMY"
    LAYER_04_SIMULATION = "LAYER_04_SIMULATION"
    LAYER_05_NAVIGATION = "LAYER_05_NAVIGATION"
    LAYER_06_DASHBOARD = "LAYER_06_DASHBOARD"
    OPERATOR = "OPERATOR"
    EXTERNAL_SENSOR = "EXTERNAL_SENSOR"


class UpdateSource(str, Enum):
    """Origin component for belief updates."""

    SENSOR_FUSION = "SENSOR_FUSION"
    LLM_ASSESSMENT = "LLM_ASSESSMENT"
    OPERATOR_INPUT = "OPERATOR_INPUT"
    THREAT_GENOME = "THREAT_GENOME"
    REPLAN_ENGINE = "REPLAN_ENGINE"
    DECISION_ENGINE = "DECISION_ENGINE"
    SECURITY_RUNTIME = "SECURITY_RUNTIME"
    MERGE_RESOLUTION = "MERGE_RESOLUTION"


class EvidenceLink(BaseModel):
    """Immutable evidence record connected to one or more hypotheses."""

    model_config = ConfigDict(frozen=True)

    evidence_id: UUID = Field(default_factory=uuid4)
    layer: EvidenceLayer
    sensor_id: Optional[str] = None
    threat_event_id: Optional[str] = None
    genome_id: Optional[str] = None
    description: str
    description_ar: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=_utc_now)
    raw_payload: Optional[Dict[str, Any]] = None


class UncertaintyMetrics(BaseModel):
    """Uncertainty characteristics for a full belief-state snapshot."""

    epistemic_uncertainty: float = Field(default=1.0, ge=0.0, le=1.0)
    aleatoric_uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)
    entropy: float = Field(default=0.0, ge=0.0)
    confidence_interval: Tuple[float, float] = (0.0, 1.0)
    staleness_seconds: float = Field(default=0.0, ge=0.0)

    @field_validator("confidence_interval")
    @classmethod
    def _validate_confidence_interval(
        cls, value: Tuple[float, float]
    ) -> Tuple[float, float]:
        lower, upper = value
        if lower > upper:
            raise ValueError("confidence_interval lower bound must be <= upper bound")
        return value


class DoctrineContext(BaseModel):
    """Doctrine/ROE context attached to a belief snapshot."""

    doctrine_type: DoctrineType = DoctrineType.UNKNOWN
    roe_code: Optional[str] = None
    engagement_auth: str = "HITL"
    escalation_level: int = Field(default=0, ge=0, le=5)
    mission_label: str = "UNNAMED"
    mission_label_ar: Optional[str] = None
    notes: Optional[str] = None


class EntityRef(BaseModel):
    """Reference to a tracked entity in the battlespace picture."""

    entity_id: UUID = Field(default_factory=uuid4)
    genome_id: Optional[str] = None
    track_id: Optional[str] = None
    label: str
    label_ar: Optional[str] = None
    entity_type: str = "UNKNOWN"
    last_seen: datetime = Field(default_factory=_utc_now)

    @field_validator("label")
    @classmethod
    def _validate_label_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("label must not be blank")
        return value


class BeliefHypothesis(BaseModel):
    """Probabilistic hypothesis tracked by the runtime."""

    hypothesis_id: UUID = Field(default_factory=uuid4)
    description: str
    description_ar: Optional[str] = None
    probability: float = Field(ge=0.0, le=1.0)
    status: HypothesisStatus = HypothesisStatus.ACTIVE
    supporting_evidence: List[EvidenceLink] = Field(default_factory=list)
    conflicting_evidence: List[EvidenceLink] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("description")
    @classmethod
    def _validate_description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @property
    def net_evidence_weight(self) -> float:
        """Return support minus contradiction confidence weight."""
        support_total = sum(item.confidence for item in self.supporting_evidence)
        conflict_total = sum(item.confidence for item in self.conflicting_evidence)
        return support_total - conflict_total

    @property
    def evidence_count(self) -> int:
        """Return total number of linked evidence artifacts."""
        return len(self.supporting_evidence) + len(self.conflicting_evidence)


class BeliefUpdate(BaseModel):
    """Immutable update request applied to the belief store."""

    model_config = ConfigDict(frozen=True)

    update_id: UUID = Field(default_factory=uuid4)
    source: UpdateSource
    author_id: Optional[str] = None
    delta: Dict[str, float] = Field(default_factory=dict)
    new_hypotheses: List[BeliefHypothesis] = Field(default_factory=list)
    retired_ids: List[str] = Field(default_factory=list)
    entity_updates: List[EntityRef] = Field(default_factory=list)
    new_evidence: Dict[str, List[EvidenceLink]] = Field(default_factory=dict)
    doctrine_update: Optional[DoctrineContext] = None
    confidence_shift: float = Field(default=0.0, ge=-1.0, le=1.0)
    justification: Optional[str] = None
    justification_ar: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utc_now)

    @field_validator("delta")
    @classmethod
    def _validate_delta_bounds(cls, value: Dict[str, float]) -> Dict[str, float]:
        for hypothesis_id, delta_value in value.items():
            if not -1.0 <= delta_value <= 1.0:
                raise ValueError(
                    f"delta for hypothesis '{hypothesis_id}' must be within [-1.0, 1.0]"
                )
        return value


class BeliefState(BaseModel):
    """Immutable runtime snapshot of entities, hypotheses, and confidence."""

    model_config = ConfigDict(frozen=True)

    state_id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=0, ge=0)
    timestamp: datetime = Field(default_factory=_utc_now)
    entities: Dict[str, EntityRef] = Field(default_factory=dict)
    hypotheses: Dict[str, BeliefHypothesis] = Field(default_factory=dict)
    confidence_distribution: Dict[str, float] = Field(default_factory=dict)
    uncertainty_metrics: UncertaintyMetrics = Field(default_factory=UncertaintyMetrics)
    evidence_links: Dict[str, EvidenceLink] = Field(default_factory=dict)
    doctrine_context: DoctrineContext = Field(default_factory=DoctrineContext)
    applied_updates: List[str] = Field(default_factory=list)
    parent_version: Optional[int] = None

    @model_validator(mode="after")
    def _validate_distribution(self) -> "BeliefState":
        if self.confidence_distribution:
            total_probability = sum(self.confidence_distribution.values())
            if abs(total_probability - 1.0) > 1e-4:
                raise ValueError(
                    "confidence_distribution must sum to 1.0 ± 1e-4 when non-empty"
                )
        for hypothesis_id in self.confidence_distribution:
            if hypothesis_id not in self.hypotheses:
                raise ValueError(
                    "confidence_distribution keys must all exist in hypotheses"
                )
        return self

    def leading_hypothesis(self) -> Optional[BeliefHypothesis]:
        """Return the hypothesis with highest current confidence."""
        if not self.confidence_distribution:
            return None
        leading_id = max(self.confidence_distribution, key=self.confidence_distribution.get)
        return self.hypotheses.get(leading_id)

    def active_hypotheses(self) -> List[BeliefHypothesis]:
        """Return active hypotheses sorted by descending probability."""
        active_items = [
            hypothesis
            for hypothesis in self.hypotheses.values()
            if hypothesis.status == HypothesisStatus.ACTIVE
        ]
        return sorted(active_items, key=lambda item: item.probability, reverse=True)

    def entropy(self) -> float:
        """Compute Shannon entropy over confidence distribution (nats)."""
        return -sum(
            probability * math.log(probability)
            for probability in self.confidence_distribution.values()
            if probability > 0.0
        )

    def diff(self, other: "BeliefState") -> Dict[str, Any]:
        """Return structural and confidence deltas between two snapshots."""
        self_hyp_ids = set(self.hypotheses.keys())
        other_hyp_ids = set(other.hypotheses.keys())
        self_entity_ids = set(self.entities.keys())
        other_entity_ids = set(other.entities.keys())

        hypotheses_added = sorted(other_hyp_ids - self_hyp_ids)
        hypotheses_removed = sorted(self_hyp_ids - other_hyp_ids)
        hypotheses_changed = sorted(
            hypothesis_id
            for hypothesis_id in (self_hyp_ids & other_hyp_ids)
            if self.hypotheses[hypothesis_id] != other.hypotheses[hypothesis_id]
        )

        entities_added = sorted(other_entity_ids - self_entity_ids)
        entities_removed = sorted(self_entity_ids - other_entity_ids)
        entities_changed = sorted(
            entity_id
            for entity_id in (self_entity_ids & other_entity_ids)
            if self.entities[entity_id] != other.entities[entity_id]
        )

        all_distribution_ids = set(self.confidence_distribution.keys()) | set(
            other.confidence_distribution.keys()
        )
        confidence_delta: Dict[str, float] = {}
        for hypothesis_id in sorted(all_distribution_ids):
            before = self.confidence_distribution.get(hypothesis_id, 0.0)
            after = other.confidence_distribution.get(hypothesis_id, 0.0)
            delta_value = after - before
            if abs(delta_value) > 0.0:
                confidence_delta[hypothesis_id] = delta_value

        return {
            "hypotheses_added": hypotheses_added,
            "hypotheses_removed": hypotheses_removed,
            "hypotheses_changed": hypotheses_changed,
            "entities_added": entities_added,
            "entities_removed": entities_removed,
            "entities_changed": entities_changed,
            "confidence_delta": confidence_delta,
        }
