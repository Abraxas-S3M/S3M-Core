"""ais-visual-fusion-extensions sensor analytics integration for S3M."""

from __future__ import annotations

import importlib

AisVisualFusionExtensionsAdapter = importlib.import_module(
    "packages.integrations.sensor_analytics.ais-visual-fusion-extensions.adapter"
).AisVisualFusionExtensionsAdapter

__all__ = ["AisVisualFusionExtensionsAdapter"]
