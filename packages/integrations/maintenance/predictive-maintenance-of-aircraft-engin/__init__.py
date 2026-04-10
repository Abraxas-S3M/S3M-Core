"""Predictive aircraft-engine maintenance integration adapter for S3M."""

from __future__ import annotations

import importlib

PredictiveMaintenanceOfAircraftAdapter = importlib.import_module(
    "packages.integrations.maintenance.predictive-maintenance-of-aircraft-engin.adapter"
).PredictiveMaintenanceOfAircraftAdapter

__all__ = ["PredictiveMaintenanceOfAircraftAdapter"]
