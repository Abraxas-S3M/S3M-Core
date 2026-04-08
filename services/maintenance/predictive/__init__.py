"""Predictive maintenance analytics interfaces for Layer 11."""

from __future__ import annotations

from typing import Any

from services.maintenance.predictive.condition_monitor import ConditionMonitor
from services.maintenance.predictive.engine import PredictiveEngine
from services.maintenance.predictive.failure_classifier import FailureClassifier
from services.maintenance.predictive.rul_estimator import RULEstimator


class PredictiveMaintenanceEngine:
    """
    Compatibility facade for sustainment workspace predictions.

    Tactical context: this adapter keeps field dashboards populated from the
    local maintenance service state when disconnected from external systems.
    """

    def get_predictions(self) -> list[dict[str, Any]]:
        try:
            from src.api.maintenance_routes import _maintenance

            source = getattr(_maintenance, "latest_predictions", {})
        except Exception:
            source = {}

        if isinstance(source, dict):
            rows = source.values()
        elif isinstance(source, list):
            rows = source
        else:
            rows = []

        payload: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                payload.append(dict(row))
            elif hasattr(row, "to_dict"):
                payload.append(row.to_dict())
            elif hasattr(row, "model_dump"):
                payload.append(row.model_dump())
        return payload


__all__ = [
    "PredictiveEngine",
    "PredictiveMaintenanceEngine",
    "RULEstimator",
    "ConditionMonitor",
    "FailureClassifier",
]
