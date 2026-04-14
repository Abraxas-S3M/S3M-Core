"""Predictive defense orchestration manager.

Military context:
Maintains deterministic, offline-safe tactical prediction state that can be
served to command-post clients without external service dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.predictive_defense.models import (
    DefenseAlert,
    DefenseCommand,
    DefensePrediction,
    GenomeContext,
    SwarmAnalysis,
    ThreatPosture,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PredictiveDefenseManager:
    """Stateful manager for tactical predictive-defense outputs."""

    def __init__(self) -> None:
        self._genome_context_by_track: Dict[str, GenomeContext] = {}
        self._predictions_by_track: Dict[str, DefensePrediction] = {}
        self._commands_by_track: Dict[str, DefenseCommand] = {}
        self._alerts: List[DefenseAlert] = []

    def get_predictions(self) -> List[DefensePrediction]:
        return list(self._predictions_by_track.values())

    def get_swarm_analysis(self) -> Optional[SwarmAnalysis]:
        predictions = self.get_predictions()
        if not predictions:
            return None

        average_threat = sum(p.threat_score for p in predictions) / len(predictions)
        swarm_detected = len(predictions) >= 3 and average_threat >= 0.6
        action = "maintain_surveillance"
        if swarm_detected:
            action = "activate_layered_intercept"
        elif average_threat >= 0.45:
            action = "prepare_interceptor_standby"

        return SwarmAnalysis(
            swarm_detected=swarm_detected,
            track_count=len(predictions),
            average_threat_score=average_threat,
            recommended_action=action,
        )

    def get_commands(self) -> List[DefenseCommand]:
        return list(self._commands_by_track.values())

    def get_alerts(self, limit: int = 20) -> List[DefenseAlert]:
        if limit <= 0:
            return []
        return self._alerts[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        posture = ThreatPosture.NORMAL
        severity = "low"
        if self._alerts:
            posture = self._alerts[-1].posture
            severity = self._alerts[-1].severity
        return {
            "tracks_with_context": len(self._genome_context_by_track),
            "predictions": len(self._predictions_by_track),
            "commands": len(self._commands_by_track),
            "alerts": len(self._alerts),
            "posture": posture.value,
            "severity": severity,
        }

    def set_genome_context(self, track_id: str, context: Dict[str, Any]) -> None:
        normalized_track = str(track_id).strip()
        if not normalized_track:
            raise ValueError("track_id required")
        if not isinstance(context, dict):
            raise ValueError("context must be an object")

        normalized_context = dict(context)
        self._genome_context_by_track[normalized_track] = GenomeContext(
            track_id=normalized_track,
            context=normalized_context,
            updated_at=_utcnow_iso(),
        )

        threat_score = self._coerce_score(normalized_context.get("threat_score"), default=0.35)
        confidence = self._coerce_score(normalized_context.get("confidence"), default=0.65)
        predicted_intent = str(normalized_context.get("predicted_intent", "observe")).strip() or "observe"
        horizon_seconds = self._coerce_horizon(normalized_context.get("horizon_seconds"), default=120)

        prediction = DefensePrediction(
            track_id=normalized_track,
            threat_score=threat_score,
            confidence=confidence,
            predicted_intent=predicted_intent,
            horizon_seconds=horizon_seconds,
        )
        self._predictions_by_track[normalized_track] = prediction

        posture = ThreatPosture.NORMAL
        severity = "low"
        action = "monitor_track"
        if threat_score >= 0.8:
            posture = ThreatPosture.HIGH
            severity = "high"
            action = "authorize_intercept_window"
        elif threat_score >= 0.5:
            posture = ThreatPosture.ELEVATED
            severity = "medium"
            action = "raise_air_defense_readiness"

        self._commands_by_track[normalized_track] = DefenseCommand(
            command_id=f"cmd-{normalized_track}",
            track_id=normalized_track,
            action=action,
            priority=severity,
            rationale=f"Threat score {threat_score:.2f} with confidence {confidence:.2f}",
        )
        self._alerts.append(
            DefenseAlert(
                alert_id=f"alert-{normalized_track}-{len(self._alerts) + 1}",
                track_id=normalized_track,
                posture=posture,
                severity=severity,
                message=f"Track {normalized_track} posture set to {posture.value}",
                timestamp=_utcnow_iso(),
            )
        )

    @staticmethod
    def _coerce_score(raw_value: Any, default: float) -> float:
        try:
            score = float(raw_value)
        except (TypeError, ValueError):
            score = default
        return max(0.0, min(1.0, score))

    @staticmethod
    def _coerce_horizon(raw_value: Any, default: int) -> int:
        try:
            horizon = int(raw_value)
        except (TypeError, ValueError):
            horizon = default
        return max(1, min(3600, horizon))

