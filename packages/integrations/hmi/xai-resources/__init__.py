"""xai_resources integration adapter for S3M."""

from __future__ import annotations

import importlib

XaiResourcesAdapter = importlib.import_module(
    "packages.integrations.hmi.xai-resources.adapter"
).XaiResourcesAdapter

__all__ = ["XaiResourcesAdapter"]
