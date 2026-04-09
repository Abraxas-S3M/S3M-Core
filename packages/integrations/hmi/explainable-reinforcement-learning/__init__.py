"""explainable-reinforcement-learning integration adapter for S3M."""

from __future__ import annotations

import importlib

ExplainableReinforcementLearningAdapter = importlib.import_module(
    "packages.integrations.hmi.explainable-reinforcement-learning.adapter"
).ExplainableReinforcementLearningAdapter

__all__ = ["ExplainableReinforcementLearningAdapter"]
