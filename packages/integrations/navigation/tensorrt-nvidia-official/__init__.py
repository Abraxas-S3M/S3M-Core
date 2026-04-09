"""TensorRT (NVIDIA official) navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

TensorrtnvidiaOfficialAdapter = importlib.import_module(
    "packages.integrations.navigation.tensorrt-nvidia-official.adapter"
).TensorrtnvidiaOfficialAdapter

__all__ = ["TensorrtnvidiaOfficialAdapter"]
