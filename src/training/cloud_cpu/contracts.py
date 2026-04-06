"""Contracts for cloud CPU training loops and resume state.

Military/tactical context:
These schemas define the minimum trusted data exchanged between the training
loop, checkpoint ladder, and dataset ingest path so interrupted field updates
can resume without guessing mutable runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class DataClass(str, Enum):
    """Classification for scenario data used in supervised updates."""

    COMMAND = "command"
    INTELLIGENCE = "intelligence"
    NAVIGATION = "navigation"
    SAFETY = "safety"


@dataclass
class TrainingExample:
    """Single supervised example emitted by the dataset cursor."""

    prompt: str
    completion: str
    domain_track: str
    data_class: DataClass
    metadata: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0

    def __post_init__(self) -> None:
        self.prompt = str(self.prompt)
        self.completion = str(self.completion)
        self.domain_track = str(self.domain_track)
        if not isinstance(self.data_class, DataClass):
            self.data_class = DataClass(str(self.data_class))
        self.weight = float(self.weight)
        if self.weight < 0.0:
            raise ValueError("TrainingExample.weight must be >= 0.0")
        if not isinstance(self.metadata, dict):
            raise TypeError("TrainingExample.metadata must be a dictionary")


@dataclass
class CycleMetrics:
    """Metrics emitted by a single micro-batch cycle."""

    cycle_id: str
    step: int
    epoch: int
    track: str
    samples_processed: int
    loss: float
    pseudo_label_acceptance_rate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TrainerState:
    """Serializable trainer state used for checkpoint resume."""

    step: int = 0
    epoch: int = 0
    last_loss: float = 0.0
    resume_count: int = 0
    total_samples: int = 0
    dataset_cursor: Dict[str, Any] = field(default_factory=dict)
    backend_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TrainerState":
        return cls(
            step=int(payload.get("step", 0)),
            epoch=int(payload.get("epoch", 0)),
            last_loss=float(payload.get("last_loss", 0.0)),
            resume_count=int(payload.get("resume_count", 0)),
            total_samples=int(payload.get("total_samples", 0)),
            dataset_cursor=dict(payload.get("dataset_cursor", {}) or {}),
            backend_state=dict(payload.get("backend_state", {}) or {}),
            metadata=dict(payload.get("metadata", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": int(self.step),
            "epoch": int(self.epoch),
            "last_loss": float(self.last_loss),
            "resume_count": int(self.resume_count),
            "total_samples": int(self.total_samples),
            "dataset_cursor": dict(self.dataset_cursor),
            "backend_state": dict(self.backend_state),
            "metadata": dict(self.metadata),
        }


@dataclass
class CheckpointMeta:
    """Normalized metadata for resume candidate checkpoints."""

    checkpoint_id: str
    step: int
    epoch: int
    loss: float
    timestamp: str
    level: int
    path: str
    sha256: str
    model_id: str
    adapter_config_hash: str
    precision_used: str
    peak_memory_mb: float
    is_complete: bool
    source: str = ""

