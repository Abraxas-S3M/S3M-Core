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

