"""Arabic-Resources communications adapter for S3M."""

from __future__ import annotations

import importlib

ArabicResourcesAdapter = importlib.import_module(
    "packages.integrations.comms.arabic-resources.adapter"
).ArabicResourcesAdapter

__all__ = ["ArabicResourcesAdapter"]
