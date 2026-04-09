"""awesome-explainable-reinforcement-learning integration adapter for S3M."""

from __future__ import annotations

import importlib

AwesomeExplainableReinforcementLearningAdapter = importlib.import_module(
    "packages.integrations.hmi.awesome-explainable-reinforcement-learni.adapter"
).AwesomeExplainableReinforcementLearningAdapter

__all__ = ["AwesomeExplainableReinforcementLearningAdapter"]
