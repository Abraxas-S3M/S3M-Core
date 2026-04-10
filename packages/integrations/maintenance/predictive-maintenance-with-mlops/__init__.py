"""Predictive Maintenance with MLOps integration wrapper for S3M."""

from __future__ import annotations

import importlib

PredictiveMaintenanceWithMlopsAdapter = importlib.import_module(
    "packages.integrations.maintenance.predictive-maintenance-with-mlops.adapter"
).PredictiveMaintenanceWithMlopsAdapter

__all__ = ["PredictiveMaintenanceWithMlopsAdapter"]
