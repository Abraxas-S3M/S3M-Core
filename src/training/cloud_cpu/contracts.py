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
from typing import Any, Dict, Optional


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


@dataclass(init=False)
class TrainerState:
    """Serializable trainer state used for checkpoint resume."""

    step: int = 0
    epoch: int = 0
    last_loss: float = 0.0
    resume_count: int = 0
    total_samples: int = 0
    run_id: str = ""
    heartbeat_at: str = ""
    dataset_cursor: Dict[str, Any] = field(default_factory=dict)
    backend_state: Dict[str, Any] = field(default_factory=dict)
    last_eval: Dict[str, float] = field(default_factory=dict)
    last_promotion: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        step: int = 0,
        epoch: int = 0,
        last_loss: float = 0.0,
        resume_count: int = 0,
        total_samples: int = 0,
        run_id: str = "",
        heartbeat_at: str = "",
        dataset_cursor: Optional[Dict[str, Any]] = None,
        backend_state: Optional[Dict[str, Any]] = None,
        last_eval: Optional[Dict[str, float]] = None,
        last_promotion: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        current_step: Any = None,
        current_epoch: Any = None,
        total_samples_processed: Any = None,
    ) -> None:
        # Accept legacy constructor aliases used by trainer_service.
        resolved_step = current_step if current_step is not None else step
        resolved_epoch = current_epoch if current_epoch is not None else epoch
        resolved_total_samples = (
            total_samples_processed if total_samples_processed is not None else total_samples
        )
        self.step = int(resolved_step)
        self.epoch = int(resolved_epoch)
        self.last_loss = float(last_loss)
        self.resume_count = int(resume_count)
        self.total_samples = int(resolved_total_samples)
        self.run_id = str(run_id)
        self.heartbeat_at = str(heartbeat_at)
        self.dataset_cursor = dict(dataset_cursor or {})
        self.backend_state = dict(backend_state or {})
        self.last_eval = dict(last_eval or {})
        self.last_promotion = dict(last_promotion or {})
        self.metadata = dict(metadata or {})

    # Compatibility aliases expected by trainer_service and legacy payloads.
    @property
    def current_step(self) -> int:
        return int(self.step)

    @current_step.setter
    def current_step(self, value: Any) -> None:
        self.step = int(value)

    @property
    def current_epoch(self) -> int:
        return int(self.epoch)

    @current_epoch.setter
    def current_epoch(self, value: Any) -> None:
        self.epoch = int(value)

    @property
    def total_samples_processed(self) -> int:
        return int(self.total_samples)

    @total_samples_processed.setter
    def total_samples_processed(self, value: Any) -> None:
        self.total_samples = int(value)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TrainerState":
        step_value = payload.get("step", payload.get("current_step", 0))
        epoch_value = payload.get("epoch", payload.get("current_epoch", 0))
        total_samples_value = payload.get("total_samples", payload.get("total_samples_processed", 0))
        return cls(
            step=int(step_value),
            epoch=int(epoch_value),
            last_loss=float(payload.get("last_loss", 0.0)),
            resume_count=int(payload.get("resume_count", 0)),
            total_samples=int(total_samples_value),
            run_id=str(payload.get("run_id", "")),
            heartbeat_at=str(payload.get("heartbeat_at", "")),
            dataset_cursor=dict(payload.get("dataset_cursor", {}) or {}),
            backend_state=dict(payload.get("backend_state", {}) or {}),
            last_eval=dict(payload.get("last_eval", {}) or {}),
            last_promotion=dict(payload.get("last_promotion", {}) or {}),
            metadata=dict(payload.get("metadata", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": int(self.step),
            "current_step": int(self.step),
            "epoch": int(self.epoch),
            "current_epoch": int(self.epoch),
            "last_loss": float(self.last_loss),
            "resume_count": int(self.resume_count),
            "total_samples": int(self.total_samples),
            "total_samples_processed": int(self.total_samples),
            "run_id": self.run_id,
            "heartbeat_at": self.heartbeat_at,
            "dataset_cursor": dict(self.dataset_cursor),
            "backend_state": dict(self.backend_state),
            "last_eval": dict(self.last_eval),
            "last_promotion": dict(self.last_promotion),
            "metadata": dict(self.metadata),
        }

    def model_dump(self) -> Dict[str, Any]:
        return self.to_dict()

    def model_copy(self, update: Optional[Dict[str, Any]] = None) -> "TrainerState":
        payload = self.to_dict()
        payload.update(update or {})
        return TrainerState.from_dict(payload)


@dataclass
class CheckpointMeta:
    """Normalized metadata for resume candidate checkpoints."""

    checkpoint_id: str
    step: int = 0
    epoch: int = 0
    loss: float = 0.0
    timestamp: str = ""
    level: int = 0
    path: str = ""
    sha256: str = ""
    model_id: str = ""
    adapter_config_hash: str = ""
    precision_used: str = ""
    peak_memory_mb: float = 0.0
    is_complete: bool = False
    run_id: str = ""
    track: str = ""
    is_promoted: bool = False
    eval_results: Dict[str, float] = field(default_factory=dict)
    samples_seen: int = 0
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "step": int(self.step),
            "epoch": int(self.epoch),
            "loss": float(self.loss),
            "timestamp": self.timestamp,
            "level": int(self.level),
            "path": self.path,
            "sha256": self.sha256,
            "model_id": self.model_id,
            "adapter_config_hash": self.adapter_config_hash,
            "precision_used": self.precision_used,
            "peak_memory_mb": float(self.peak_memory_mb),
            "is_complete": bool(self.is_complete),
            "run_id": self.run_id,
            "track": self.track,
            "is_promoted": bool(self.is_promoted),
            "eval_results": dict(self.eval_results),
            "samples_seen": int(self.samples_seen),
            "source": self.source,
        }

    def model_dump(self) -> Dict[str, Any]:
        return self.to_dict()

    def model_copy(self, update: Optional[Dict[str, Any]] = None) -> "CheckpointMeta":
        payload = self.to_dict()
        payload.update(update or {})
        return CheckpointMeta(**payload)


@dataclass
class PromotionDecision:
    """Decision on whether to promote a trained adapter to the merged model pool."""

    adapter_id: str
    engine_id: str
    track: str
    promoted: bool
    reason: str
    eval_score: float = 0.0
    grok_verdict: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "engine_id": self.engine_id,
            "track": self.track,
            "promoted": self.promoted,
            "reason": self.reason,
            "eval_score": float(self.eval_score),
            "grok_verdict": self.grok_verdict,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }

