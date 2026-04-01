"""Composed predictive maintenance engine for Layer 11."""

from __future__ import annotations

from services.maintenance.models import Asset, AssetType, RULPrediction, SensorTelemetry
from services.maintenance.predictive.condition_monitor import ConditionMonitor
from services.maintenance.predictive.failure_classifier import FailureClassifier
from services.maintenance.predictive.rul_estimator import RULEstimator


class PredictiveEngine:
    """Wrapper that combines condition, failure, and RUL analytics."""

    def __init__(self, model_backend: str = "auto") -> None:
        self.rul_estimator = RULEstimator(model_backend=model_backend)
        self.condition_monitor = ConditionMonitor()
        self.failure_classifier = FailureClassifier()

    def predict_rul(self, asset: Asset, telemetry_history: list[SensorTelemetry]) -> RULPrediction:
        return self.rul_estimator.predict(telemetry_history=telemetry_history, asset=asset)

    def assess_condition(self, telemetry: SensorTelemetry) -> dict:
        return self.condition_monitor.evaluate(telemetry)

    def classify_failure(self, telemetry: SensorTelemetry, asset_type: AssetType) -> dict:
        return self.failure_classifier.classify(telemetry=telemetry, asset_type=asset_type)

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "rul_estimator": self.rul_estimator.get_model_info(),
            "condition_monitor": "ready",
            "failure_classifier": "ready",
        }
