"""Fleetbase maintenance integration wrapper for S3M."""

from __future__ import annotations

import importlib

FleetbaseAdapter = importlib.import_module(
    "packages.integrations.maintenance.fleetbase.adapter"
).FleetbaseAdapter

__all__ = ["FleetbaseAdapter"]
