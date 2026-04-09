"""LLM-controlled-drone HMI integration adapter for S3M."""

from __future__ import annotations

import importlib

LlmControlledDroneAdapter = importlib.import_module(
    "packages.integrations.hmi.llm-controlled-drone.adapter"
).LlmControlledDroneAdapter

__all__ = ["LlmControlledDroneAdapter"]
