"""SC-LIO-SAM navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

ScLioSamAdapter = importlib.import_module(
    "packages.integrations.navigation.sc-lio-sam.adapter"
).ScLioSamAdapter

__all__ = ["ScLioSamAdapter"]
