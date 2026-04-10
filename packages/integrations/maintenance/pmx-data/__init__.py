"""PMX Data maintenance integration wrapper for S3M."""

from __future__ import annotations

import importlib

PmxDataAdapter = importlib.import_module(
    "packages.integrations.maintenance.pmx-data.adapter"
).PmxDataAdapter

__all__ = ["PmxDataAdapter"]
