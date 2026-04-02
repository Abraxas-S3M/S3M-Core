"""Continuous tactical risk evaluation for real-time overrides."""

from __future__ import annotations

from collections import deque
import math
from typing import Any, Deque, Dict


class RiskAssessor:
    """Evaluates multi-dimensional mission risk and trend over time."""

    def __init__(self, window_size: int = 10) -> None:
        self.window_size = max(3, int(window_size))
        self._history: Deque[float] = deque(maxlen=self.window_size)
        self.weights = {
            "threat_proximity": 0.30,
            "resource_depletion": 0.25,
            "comms_degradation": 0.15,
            "roe_violation": 0.20,
            "mission_exposure": 0.10,
        }
        self.thresholds = {
            "abort": 0.75,
            "replan": 0.55,
            "escalate": 0.65,
            "reassess": 0.45,
        }

    def _sigmoid(self, x: float, midpoint: float, sharpness: float = 8.0) -> float:
        z = sharpness * (x - midpoint)
        return 1.0 / (1.0 + math.exp(-z))

    def assess(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Assess current tactical risk and derive control gates."""
        distance = float(context.get("threat_distance", context.get("nearest_threat_distance", 200.0)))
        battery = float(context.get("battery_pct", 100.0))
        fuel = float(context.get("fuel_pct", 100.0))
        comms_quality = float(context.get("comms_quality", 1.0))
        comms_status = str(context.get("comms_status", "nominal")).lower()
        roe_violation_flag = bool(context.get("roe_violation", False))
        roe = str(context.get("rules_of_engagement", "weapons_tight")).lower()
        proposed_action = str(context.get("proposed_action", "hold")).lower()
        mission_exposure = float(context.get("mission_exposure", 0.2))

        threat_proximity = self._sigmoid(max(0.0, 1.0 - (distance / 120.0)), midpoint=0.45)
        resource_depletion = self._sigmoid(max(0.0, 1.0 - ((battery + fuel) / 200.0)), midpoint=0.35)
        if comms_status == "lost" or comms_quality <= 0.1:
            comms_degradation = 1.0
        elif comms_status == "degraded" or comms_quality <= 0.5:
            comms_degradation = 0.65
        else:
            comms_degradation = 0.05
        roe_violation = 1.0 if (roe_violation_flag or (roe == "weapons_hold" and proposed_action == "engage")) else 0.0
        mission_exposure_score = self._sigmoid(max(0.0, min(1.0, mission_exposure)), midpoint=0.5)

        profile = {
            "threat_proximity": threat_proximity,
            "resource_depletion": resource_depletion,
            "comms_degradation": comms_degradation,
            "roe_violation": roe_violation,
            "mission_exposure": mission_exposure_score,
        }
        composite = 0.0
        for key, value in profile.items():
            composite += self.weights[key] * float(value)
        composite = max(0.0, min(1.0, composite))
        self._history.append(composite)
        risk_trend = self.risk_trend()

        decision_gate = "continue"
        if composite >= self.thresholds["abort"]:
            decision_gate = "abort"
        elif composite >= self.thresholds["escalate"]:
            decision_gate = "escalate"
        elif composite >= self.thresholds["replan"]:
            decision_gate = "replan"
        elif composite >= self.thresholds["reassess"]:
            decision_gate = "reassess"

        return {
            "risk_score": composite,
            "risk_profile": profile,
            "decision_gate": decision_gate,
            "risk_trend": risk_trend,
            # Backward-compatible aliases.
            "score": composite,
            "profile": profile,
            "trend": risk_trend,
            "gate": decision_gate,
        }

    def risk_trend(self) -> str:
        """Return risk trend label from sliding-window history."""
        if len(self._history) < 3:
            return "stable"
        first = self._history[0]
        last = self._history[-1]
        delta = last - first
        if delta > 0.08:
            return "escalating"
        if delta < -0.08:
            return "de_escalating"
        return "stable"

    def trend(self) -> str:
        """Compatibility wrapper for legacy callers."""
        return self.risk_trend()

    def history(self) -> list[float]:
        return list(self._history)

