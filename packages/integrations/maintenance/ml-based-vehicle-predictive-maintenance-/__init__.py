"""ML-based vehicle predictive maintenance integration wrapper for S3M."""

from __future__ import annotations

import importlib

MlBasedVehiclePredictiveAdapter = importlib.import_module(
    "packages.integrations.maintenance.ml-based-vehicle-predictive-maintenance-.adapter"
).MlBasedVehiclePredictiveAdapter

__all__ = ["MlBasedVehiclePredictiveAdapter"]
