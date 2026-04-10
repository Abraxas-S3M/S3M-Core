"""msdllib-orbat-mapper training_sim integration wrapper for S3M."""

from __future__ import annotations

import importlib

MsdlliborbatMapperAdapter = importlib.import_module(
    "packages.integrations.training_sim.msdllib-orbat-mapper.adapter"
).MsdlliborbatMapperAdapter

__all__ = ["MsdlliborbatMapperAdapter"]
