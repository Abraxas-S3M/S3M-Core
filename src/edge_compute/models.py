"""Models for edge self-training pipelines.

Defines strategy selection and pseudo-labeling batch metadata used by the
self-training engine that runs on disconnected tactical edge hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SelfTrainingStrategy(str, Enum):
    """Supported self-training strategies for edge adaptation."""

    NOISY_STUDENT = "noisy_student"
    PSEUDO_LABEL = "pseudo_label"
    CO_TRAINING = "co_training"


@dataclass
class PseudoLabelBatch:
    """Summary of pseudo-label output for one self-training cycle."""

    strategy: SelfTrainingStrategy
    sample_count: int
    avg_confidence: float
    noise_applied: bool = False
