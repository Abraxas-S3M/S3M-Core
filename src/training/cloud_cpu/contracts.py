"""Shared data contracts for cloud CPU training orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.training.cloud_cpu.paths import TrainingTrack


class DataClass(str, Enum):
    """Scenario data classes used for operational adaptation."""

    COMMAND = "command"
    COP_INTEL = "cop_intel"
    RISK_READINESS = "risk_readiness"
    BILINGUAL = "bilingual"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScenarioManifest(BaseModel):
    """Scenario pack metadata contract for mission-specific training input."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    track: TrainingTrack
    data_class: DataClass
    prompt_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=_utc_now)
    version: str
    checksum: str


class TrainingExample(BaseModel):
    """Prompt-completion training example contract for one tactical sample."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    completion: str
    domain_track: TrainingTrack
    data_class: DataClass
    metadata: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(default=1.0, ge=0.0)


class CheckpointMeta(BaseModel):
    """Checkpoint metadata written into state manifests for resume safety."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str
    run_id: str
    track: TrainingTrack
    step: int = Field(ge=0)
    epoch: int = Field(ge=0)
    loss: float
    is_complete: bool
    is_promoted: bool
    sha256: str
    timestamp: datetime = Field(default_factory=_utc_now)
    eval_results: dict[str, Any] = Field(default_factory=dict)


class TrainerState(BaseModel):
    """Serialized trainer progress for resilient loop recovery."""

    model_config = ConfigDict(frozen=True)

    current_step: int = Field(ge=0)
    current_epoch: int = Field(ge=0)
    dataset_cursor: dict[str, int] = Field(default_factory=dict)
    last_eval: dict[str, Any] = Field(default_factory=dict)
    last_promotion: dict[str, Any] = Field(default_factory=dict)
    run_id: str
    started_at: datetime = Field(default_factory=_utc_now)
    heartbeat_at: datetime = Field(default_factory=_utc_now)


class CycleMetrics(BaseModel):
    """Per-cycle telemetry contract for training and promotion observability."""

    model_config = ConfigDict(frozen=True)

    cycle_id: str
    step: int = Field(ge=0)
    epoch: int = Field(ge=0)
    track: TrainingTrack
    samples_processed: int = Field(ge=0)
    loss: float
    pseudo_label_acceptance_rate: float = Field(ge=0.0, le=1.0)
    eval_score: float
    checkpoint_age_seconds: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=_utc_now)


class PromotionDecision(BaseModel):
    """Promotion gate decision contract for checkpoint governance."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str
    track: TrainingTrack
    passed: bool
    eval_scores: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    promoted_at: datetime | None = None
    reason: str
