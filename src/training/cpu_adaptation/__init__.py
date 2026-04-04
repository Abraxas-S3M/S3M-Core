"""CPU adaptation entrypoints for austere edge learning loops."""

from src.training.cpu_adaptation.adapter_tuner import AdapterConfig, CPUAdapterTuner, TrainingResult
from src.training.cpu_adaptation.classifier_retrainer import CPUClassifierRetrainer, ClassifierResult
from src.training.cpu_adaptation.survival_distiller import (
    DistillationResult,
    DistillationTrigger,
    SurvivalDistiller,
    SurvivalStudentConfig,
)

try:
    from src.training.cpu_adaptation.chunk_recurrent_trainer import (
        ChunkRecurrentTrainer,
        ChunkTrainingConfig,
        PagedKVCache,
    )
except Exception:  # pragma: no cover - optional torch dependency guard
    ChunkRecurrentTrainer = None  # type: ignore[assignment]
    ChunkTrainingConfig = None  # type: ignore[assignment]
    PagedKVCache = None  # type: ignore[assignment]

__all__ = [
    "AdapterConfig",
    "CPUAdapterTuner",
    "CPUClassifierRetrainer",
    "ChunkRecurrentTrainer",
    "ChunkTrainingConfig",
    "PagedKVCache",
    "TrainingResult",
    "ClassifierResult",
    "CPUEvaluationHarness",
    "SurvivalDistiller",
    "SurvivalStudentConfig",
    "DistillationTrigger",
    "DistillationResult",
]
