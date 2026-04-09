"""jetson-inference navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

JetsonInferenceAdapter = importlib.import_module(
    "packages.integrations.navigation.jetson-inference.adapter"
).JetsonInferenceAdapter

__all__ = ["JetsonInferenceAdapter"]
