"""CPU adaptation entrypoints for austere edge learning loops."""

from src.training.cpu_adaptation.adapter_tuner import AdapterConfig, CPUAdapterTuner, TrainingResult
from src.training.cpu_adaptation.classifier_retrainer import CPUClassifierRetrainer, ClassifierResult
from src.training.cpu_adaptation.chunk_recurrent_trainer import (
    ChunkRecurrentTrainer,
    ChunkTrainingConfig,
    PagedKVCache,
)

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
]
