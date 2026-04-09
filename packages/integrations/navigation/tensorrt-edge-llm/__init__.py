"""TensorRT-Edge-LLM navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

TensorrtEdgeLlmAdapter = importlib.import_module(
    "packages.integrations.navigation.tensorrt-edge-llm.adapter"
).TensorrtEdgeLlmAdapter

__all__ = ["TensorrtEdgeLlmAdapter"]
