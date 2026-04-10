"""S3M training_sim integration wrapper for LLMWargaming."""

from __future__ import annotations

import importlib

LlmwargamingAdapter = importlib.import_module(
    "packages.integrations.training_sim.llmwargaming.adapter"
).LlmwargamingAdapter

__all__ = ["LlmwargamingAdapter"]
