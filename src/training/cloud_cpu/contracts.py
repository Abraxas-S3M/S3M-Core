"""Contracts for cloud CPU training loops and resume state.

Military/tactical context:
These schemas define the minimum trusted data exchanged between the training
loop, checkpoint ladder, and dataset ingest path so interrupted field updates
can resume without guessing mutable runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class DataClass(str, Enum):
    """Classification for scenario data used in supervised updates."""

    COMMAND = "command"
    COP_INTEL = "cop_intel"
    RISK_READINESS = "risk_readiness"
    BILINGUAL = "bilingual"
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
    dataset_cursor: Dict[str, Any] = field(default_factory=dict)
    backend_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    heartbeat_at: str = ""
    last_eval: Dict[str, float] = field(default_factory=dict)
    last_promotion: Dict[str, Any] = field(default_factory=dict)
    def __init__(
        self,
        step: int = 0,
        epoch: int = 0,
        last_loss: float = 0.0,
        resume_count: int = 0,
        total_samples: int = 0,
        dataset_cursor: Dict[str, Any] | None = None,
        backend_state: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
        run_id: str = "",
        heartbeat_at: str = "",
        last_eval: Dict[str, float] | None = None,
        last_promotion: Dict[str, Any] | None = None,
        current_step: int | None = None,
        current_epoch: int | None = None,
        total_samples_processed: int | None = None,
    ) -> None:
        if current_step is not None:
            step = int(current_step)
        if current_epoch is not None:
            epoch = int(current_epoch)
        if total_samples_processed is not None:
            total_samples = int(total_samples_processed)

        self.step = int(step)
        self.epoch = int(epoch)
        self.last_loss = float(last_loss)
        self.resume_count = int(resume_count)
        self.total_samples = int(total_samples)
        self.run_id = str(run_id)
        self.heartbeat_at = str(heartbeat_at)

        self.dataset_cursor = dict(dataset_cursor or {})
        self.backend_state = dict(backend_state or {})
        self.metadata = dict(metadata or {})
        self.last_eval = dict(last_eval or {})
        self.last_promotion = dict(last_promotion or {})

        if dataset_cursor is not None and not isinstance(dataset_cursor, dict):
            raise TypeError("TrainerState.dataset_cursor must be a dictionary")
        if backend_state is not None and not isinstance(backend_state, dict):
            raise TypeError("TrainerState.backend_state must be a dictionary")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("TrainerState.metadata must be a dictionary")
        if last_eval is not None and not isinstance(last_eval, dict):
            raise TypeError("TrainerState.last_eval must be a dictionary")
        if last_promotion is not None and not isinstance(last_promotion, dict):
            raise TypeError("TrainerState.last_promotion must be a dictionary")

    @property
    def current_step(self) -> int:
        return int(self.step)

    @current_step.setter
    def current_step(self, value: int) -> None:
        self.step = int(value)

    @property
    def current_epoch(self) -> int:
        return int(self.epoch)

    @current_epoch.setter
    def current_epoch(self, value: int) -> None:
        self.epoch = int(value)

    @property
    def total_samples_processed(self) -> int:
        return int(self.total_samples)

    @total_samples_processed.setter
    def total_samples_processed(self, value: int) -> None:
        self.total_samples = int(value)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TrainerState":
        step = payload.get("step", payload.get("current_step", 0))
        epoch = payload.get("epoch", payload.get("current_epoch", 0))
        total_samples = payload.get("total_samples", payload.get("total_samples_processed", 0))
        return cls(
            step=int(step),
            epoch=int(epoch),
            last_loss=float(payload.get("last_loss", 0.0)),
            resume_count=int(payload.get("resume_count", 0)),
            total_samples=int(total_samples),
            dataset_cursor=dict(payload.get("dataset_cursor", {}) or {}),
            backend_state=dict(payload.get("backend_state", {}) or {}),
            metadata=dict(payload.get("metadata", {}) or {}),
            run_id=str(payload.get("run_id", "")),
            heartbeat_at=str(payload.get("heartbeat_at", "")),
            last_eval=dict(payload.get("last_eval", {}) or {}),
            last_promotion=dict(payload.get("last_promotion", {}) or {}),
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
            "run_id": self.run_id,
            "heartbeat_at": self.heartbeat_at,
            "last_eval": dict(self.last_eval),
            "last_promotion": dict(self.last_promotion),
            "current_step": int(self.step),
            "current_epoch": int(self.epoch),
            "total_samples_processed": int(self.total_samples),
        }

    def model_dump(self) -> Dict[str, Any]:
        return self.to_dict()

    def model_copy(self, update: Dict[str, Any] | None = None) -> "TrainerState":
        payload = self.to_dict()
        if update:
            payload.update(update)
        return TrainerState.from_dict(payload)


@dataclass
class CheckpointMeta:
    """Normalized metadata for resume candidate checkpoints."""

    checkpoint_id: str
    step: int
    epoch: int = 0
    loss: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: int = 0
    path: str = ""
    sha256: str = ""
    model_id: str = ""
    adapter_config_hash: str = ""
    precision_used: str = "unknown"
    peak_memory_mb: float = 0.0
    is_complete: bool = False
    source: str = ""
    run_id: str = ""
    track: str = ""
    is_promoted: bool = False
    eval_results: Dict[str, float] = field(default_factory=dict)
    samples_seen: int = 0

    def __post_init__(self) -> None:
        self.checkpoint_id = str(self.checkpoint_id)
        self.step = int(self.step)
        self.epoch = int(self.epoch)
        self.loss = float(self.loss)
        self.timestamp = str(self.timestamp)
        self.level = int(self.level)
        self.path = str(self.path)
        self.sha256 = str(self.sha256)
        self.model_id = str(self.model_id)
        self.adapter_config_hash = str(self.adapter_config_hash)
        self.precision_used = str(self.precision_used)
        self.peak_memory_mb = float(self.peak_memory_mb)
        self.source = str(self.source)
        self.run_id = str(self.run_id)
        self.track = str(self.track)
        self.samples_seen = int(self.samples_seen)
        if not isinstance(self.eval_results, dict):
            raise TypeError("CheckpointMeta.eval_results must be a dictionary")

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)

    def model_copy(self, update: Dict[str, Any] | None = None) -> "CheckpointMeta":
        payload = self.model_dump()
        if update:
            payload.update(update)
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

