"""Model-Inference-Deployment navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

ModelInferenceDeploymentAdapter = importlib.import_module(
    "packages.integrations.navigation.model-inference-deployment.adapter"
).ModelInferenceDeploymentAdapter

__all__ = ["ModelInferenceDeploymentAdapter"]
