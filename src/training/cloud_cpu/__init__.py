"""Cloud CPU training package for continuous track adaptation."""

from src.training.cloud_cpu.contracts import (
    CheckpointMeta,
    CycleMetrics,
    DataClass,
    TrainerState,
    TrainingExample,
)
from src.training.cloud_cpu.dataset_cursor import DatasetCursor
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.resume_manager import ResumeManager
from src.training.cloud_cpu.track_router import TrackRouter
from src.training.cloud_cpu.training_loop import StubTrainingBackend, TrainingBackend, TrainingLoop

# Merge-safety: newer branches may provide cloud CPU promotion/metrics controls.
try:  # pragma: no cover - optional cross-branch compatibility
    from src.training.cloud_cpu.contracts import PromotionDecision  # type: ignore
except Exception:  # pragma: no cover - optional cross-branch compatibility
    PromotionDecision = None  # type: ignore[assignment]

try:  # pragma: no cover - optional cross-branch compatibility
    from src.training.cloud_cpu.metrics_store import MetricsStore  # type: ignore
except Exception:  # pragma: no cover - optional cross-branch compatibility
    MetricsStore = None  # type: ignore[assignment]

try:  # pragma: no cover - optional cross-branch compatibility
    from src.training.cloud_cpu.promotion_gate import PromotionGate  # type: ignore
except Exception:  # pragma: no cover - optional cross-branch compatibility
    PromotionGate = None  # type: ignore[assignment]

try:  # pragma: no cover - optional cross-branch compatibility
    from src.training.cloud_cpu.resource_guard import (  # type: ignore
        ResourceGuard,
        ResourceStatus,
        ThrottleAction,
    )
except Exception:  # pragma: no cover - optional cross-branch compatibility
    ResourceGuard = None  # type: ignore[assignment]
    ResourceStatus = None  # type: ignore[assignment]
    ThrottleAction = None  # type: ignore[assignment]

__all__ = [
    "CheckpointMeta",
    "CycleMetrics",
    "DataClass",
    "DatasetCursor",
    "ResumeManager",
    "StatePaths",
    "StubTrainingBackend",
    "TrackRouter",
    "TrainerState",
    "TrainingBackend",
    "TrainingExample",
    "TrainingLoop",
    "TrainingTrack",
]

if PromotionDecision is not None:
    __all__.append("PromotionDecision")
if MetricsStore is not None:
    __all__.append("MetricsStore")
if PromotionGate is not None:
    __all__.append("PromotionGate")
if ResourceGuard is not None:
    __all__.append("ResourceGuard")
if ResourceStatus is not None:
    __all__.append("ResourceStatus")
if ThrottleAction is not None:
    __all__.append("ThrottleAction")

