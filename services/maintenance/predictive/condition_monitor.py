"""Condition monitor for military platform telemetry health assessment."""

from __future__ import annotations

from typing import Dict, List, Optional

from services.maintenance.models import Asset, AssetCondition, SensorTelemetry


class ConditionMonitor:
    """Evaluate sensor readings and trends for readiness-driven maintenance triggers."""

    def __init__(self, thresholds: Optional[dict] = None):
        self.thresholds = thresholds or {
            "temperature_c": {"warning": 450, "critical": 520},
            "vibration_g": {"warning": 3.5, "critical": 5.0},
            "pressure_psi": {"warning_low": 25, "critical_low": 20},
            "oil_temp_c": {"warning": 110, "critical": 130},
            "rpm_deviation_pct": {"warning": 5, "critical": 10},
        }

    def evaluate(self, telemetry: SensorTelemetry) -> dict:
        alerts: List[dict] = []
        readings_status: Dict[str, str] = {}
        has_warning = False
        has_critical = False

        for sensor, value in telemetry.readings.items():
            if not isinstance(value, (int, float)):
                readings_status[sensor] = "unknown"
                continue
            status = "normal"
            t = self.thresholds.get(sensor)
            if t:
                numeric = float(value)
                if "critical" in t and numeric >= float(t["critical"]):
                    status = "critical"
                    has_critical = True
                    alerts.append({"sensor": sensor, "value": numeric, "threshold": t["critical"], "severity": "critical"})
                elif "warning" in t and numeric >= float(t["warning"]):
                    status = "warning"
                    has_warning = True
                    alerts.append({"sensor": sensor, "value": numeric, "threshold": t["warning"], "severity": "warning"})
                elif "critical_low" in t and numeric <= float(t["critical_low"]):
                    status = "critical"
                    has_critical = True
                    alerts.append({"sensor": sensor, "value": numeric, "threshold": t["critical_low"], "severity": "critical"})
                elif "warning_low" in t and numeric <= float(t["warning_low"]):
                    status = "warning"
                    has_warning = True
                    alerts.append({"sensor": sensor, "value": numeric, "threshold": t["warning_low"], "severity": "warning"})
            readings_status[sensor] = status

        condition = AssetCondition.GOOD
        if has_critical:
            condition = AssetCondition.CRITICAL
        elif has_warning:
            condition = AssetCondition.FAIR

        return {
            "asset_id": telemetry.asset_id,
            "condition": condition,
            "alerts": alerts,
            "readings_status": readings_status,
        }

    def evaluate_trend(self, history: List[SensorTelemetry], window: int = 10) -> dict:
        if not history:
            return {"trends": {}, "degrading_sensors": [], "trend_risk": "low"}

        sample = history[-max(2, window):]
        sensors = sorted({k for h in sample for k in h.readings.keys() if isinstance(h.readings.get(k), (int, float))})
        trends: Dict[str, float] = {}
        degrading: List[str] = []

        for sensor in sensors:
            values = [float(h.readings.get(sensor, 0.0)) for h in sample]
            slope = (values[-1] - values[0]) / max(1, len(values) - 1)
            trends[sensor] = slope
            t = self.thresholds.get(sensor)
            if not t:
                continue
            if "critical" in t and slope > 0:
                pct = (slope / max(1e-6, float(t["critical"]))) * 100.0
                if pct > 1.0:
                    degrading.append(sensor)
            if "critical_low" in t and slope < 0:
                pct = (abs(slope) / max(1e-6, float(t["critical_low"]))) * 100.0
                if pct > 1.0:
                    degrading.append(sensor)

        if len(degrading) >= 3:
            risk = "critical"
        elif len(degrading) == 2:
            risk = "high"
        elif len(degrading) == 1:
            risk = "medium"
        else:
            risk = "low"

        return {"trends": trends, "degrading_sensors": sorted(set(degrading)), "trend_risk": risk}

    def generate_condition_report(self, asset: Asset, telemetry_history: List[SensorTelemetry]) -> str:
        latest = telemetry_history[-1] if telemetry_history else None
        condition = self.evaluate(latest)["condition"].value if latest else asset.condition.value
        trends = self.evaluate_trend(telemetry_history)

        prompt = (
            f"Generate a maintenance condition report for {asset.designation}: current readings "
            f"{latest.readings if latest else {}} , trends {trends}, condition {condition}. "
            "Include: 1) Assessment 2) Risk areas 3) Recommended actions."
        )

        try:
            from src.llm_core.inference import S3MInference

            text = S3MInference().generate(prompt, max_tokens=300)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass

        # Tactical fallback keeps operators informed in disconnected deployments.
        return (
            f"Maintenance Condition Report - {asset.designation}\n"
            f"Assessment: Current condition is {condition}.\n"
            f"Risk Areas: {', '.join(trends['degrading_sensors']) if trends['degrading_sensors'] else 'No significant degrading trends.'}\n"
            "Recommended Actions: Increase monitoring frequency, schedule inspection for flagged subsystems, and preserve mission readiness margin."
        )
