"""
S3M cloud CPU continuous training system for domain-adaptive military workflows.

This package defines shared contracts for cloud-side training orchestration so
checkpoint promotion, scenario ingestion, and cycle telemetry remain consistent
across Saudi MOD, Ukraine MOD, NATO, and shared tactical data tracks.
"""

from src.training.cloud_cpu.contracts import (
    CheckpointMeta,
    CycleMetrics,
    PromotionDecision,
    ScenarioManifest,
    TrainerState,
    TrainingExample,
)
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack

__all__ = [
    "StatePaths",
    "TrainingTrack",
    "ScenarioManifest",
    "TrainingExample",
    "CheckpointMeta",
    "TrainerState",
    "CycleMetrics",
    "PromotionDecision",
]
