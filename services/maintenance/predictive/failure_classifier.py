"""Rule-based tactical failure mode classifier for maintenance telemetry."""

from __future__ import annotations

from typing import List

from services.maintenance.models import AssetType, SensorTelemetry


class FailureClassifier:
    """Classify likely failure modes from high-signal telemetry signatures."""

    def __init__(self) -> None:
        self._thresholds = {
            "temperature_c": 500.0,
            "vibration_g": 5.0,
            "oil_temp_c": 120.0,
            "pressure_psi": 20.0,
            "rpm_deviation_pct": 10.0,
        }

    def classify(self, telemetry: SensorTelemetry, asset_type: AssetType) -> dict:
        readings = telemetry.readings
        temp = float(readings.get("temperature_c", 0.0))
        vibration = float(readings.get("vibration_g", 0.0))
        pressure = float(readings.get("pressure_psi", 999.0))
        oil_temp = float(readings.get("oil_temp_c", 0.0))
        rpm_dev = float(readings.get("rpm_deviation_pct", 0.0))

        contributing: List[str] = []
        failure_mode = "gradual_wear"
        confidence = 0.55
        severity = "low"

        if temp >= self._thresholds["temperature_c"] and vibration >= self._thresholds["vibration_g"]:
            failure_mode = "bearing_degradation"
            confidence = 0.91
            severity = "critical"
            contributing = ["temperature_c", "vibration_g"]
        elif temp >= self._thresholds["temperature_c"] and vibration < self._thresholds["vibration_g"]:
            failure_mode = "combustion_issue"
            confidence = 0.83
            severity = "high"
            contributing = ["temperature_c"]
        elif pressure <= self._thresholds["pressure_psi"] and oil_temp >= self._thresholds["oil_temp_c"]:
            failure_mode = "seal_leak"
            confidence = 0.86
            severity = "high"
            contributing = ["pressure_psi", "oil_temp_c"]
        elif rpm_dev >= self._thresholds["rpm_deviation_pct"]:
            failure_mode = "control_system_fault"
            confidence = 0.79
            severity = "high"
            contributing = ["rpm_deviation_pct"]
        elif vibration >= self._thresholds["vibration_g"] and temp < self._thresholds["temperature_c"]:
            if asset_type in {AssetType.AIRCRAFT, AssetType.FIGHTER_JET, AssetType.HELICOPTER, AssetType.UAV}:
                failure_mode = "blade_imbalance"
            else:
                failure_mode = "alignment_issue"
            confidence = 0.77
            severity = "medium"
            contributing = ["vibration_g"]

        return {
            "failure_mode": failure_mode,
            "confidence": confidence,
            "contributing_sensors": contributing,
            "severity": severity,
        }

    def classify_batch(self, telemetry_list: List[SensorTelemetry], asset_type: AssetType) -> List[dict]:
        return [self.classify(telemetry=item, asset_type=asset_type) for item in telemetry_list]
