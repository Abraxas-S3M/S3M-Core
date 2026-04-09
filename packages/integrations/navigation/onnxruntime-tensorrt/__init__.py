"""Onnxruntime-TensorRT navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

OnnxruntimeTensorrtAdapter = importlib.import_module(
    "packages.integrations.navigation.onnxruntime-tensorrt.adapter"
).OnnxruntimeTensorrtAdapter

__all__ = ["OnnxruntimeTensorrtAdapter"]
