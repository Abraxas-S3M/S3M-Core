"""
S3M Continuous Evolution System.

Closes the learning loop:
Sensor -> decision -> outcome -> feedback -> replay -> retrain -> promote/rollback.
"""

from .continuous_loop import ContinuousEvolutionLoop, EvolutionConfig, EvolutionCycle
from .experience_replay import Experience, PrioritizedReplayBuffer
from .model_versioner import ModelVersion, ModelVersioner

__all__ = [
    "ContinuousEvolutionLoop",
    "EvolutionConfig",
    "EvolutionCycle",
    "PrioritizedReplayBuffer",
    "Experience",
    "ModelVersioner",
    "ModelVersion",
]
