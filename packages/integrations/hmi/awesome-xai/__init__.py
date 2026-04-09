"""awesome-xai integration adapter for S3M."""

from __future__ import annotations

import importlib

AwesomeXaiAdapter = importlib.import_module(
    "packages.integrations.hmi.awesome-xai.adapter"
).AwesomeXaiAdapter

__all__ = ["AwesomeXaiAdapter"]
