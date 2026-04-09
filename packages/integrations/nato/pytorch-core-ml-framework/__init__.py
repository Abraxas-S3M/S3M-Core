"""PyTorch core ML framework integration adapter for S3M."""

from __future__ import annotations

import importlib

PytorchcoreMlFrameworkAdapter = importlib.import_module(
    "packages.integrations.nato.pytorch-core-ml-framework.adapter"
).PytorchcoreMlFrameworkAdapter

__all__ = ["PytorchcoreMlFrameworkAdapter"]
