"""Cross-layer alert aggregation manager for dashboard operations."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.dashboard.providers.autonomy_dash_provider import AutonomyDashProvider
from src.dashboard.providers.system_health_provider import SystemHealthProvider
from src.dashboard.providers.threat_dash_provider import ThreatDashProvider

_SEVERITY_ORDER: Dict[str, int] = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFO": 4,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlertManager:
    """Unify actionable alerts across threat, autonomy, and system layers."""

    def __init__(
        self,
        max_alerts: int = 500,
        threat_provider: Optional[ThreatDashProvider] = None,
        autonomy_provider: Optional[AutonomyDashProvider] = None,
        system_provider: Optional[SystemHealthProvider] = None,
    ) -> None:
        if not isinstance(max_alerts, int) or max_alerts <= 0:
            raise ValueError("max_alerts must be a positive integer")
        self.max_alerts = max_alerts
        self.threat_provider = threat_provider or ThreatDashProvider()
        self.autonomy_provider = autonomy_provider or AutonomyDashProvider()
        self.system_provider = system_provider or SystemHealthProvider()
        self._active: List[Dict[str, Any]] = []
        self._dismissed: Set[str] = set()

    @staticmethod
    def _normalized_level(level: Any) -> str:
        val = str(level or "INFO").upper()
        return val if val in _SEVERITY_ORDER else "INFO"

    @staticmethod
    def _alert_id(parts: List[str]) -> str:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest[:20]

    def _build_threat_alerts(self) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        feed = self.threat_provider.get_threat_feed(limit=300)
        for event in feed:
            level = self._normalized_level(event.get("level"))
            if level not in {"HIGH", "CRITICAL"}:
                continue
            title = f"{level} threat event"
            message = str(event.get("title") or event.get("description") or "Threat detected")
            alert_id = self._alert_id([level, "threat_detection", str(event.get("id", "")), message])
            alerts.append(
                {
                    "alert_id": alert_id,
                    "timestamp": str(event.get("timestamp", _utcnow())),
                    "level": level,
                    "source_layer": "threat_detection",
                    "title": title,
                    "message": message,
                    "action_url": "/dashboard/threats/feed",
                }
            )
        return alerts

    def _build_review_alerts(self) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        for decision in self.autonomy_provider.get_review_queue():
            decision_id = str(decision.get("id", "unknown"))
            risk = float(decision.get("risk_score", 0.0))
            level = "CRITICAL" if risk >= 0.85 else "HIGH"
            message = (
                f"Decision {decision_id} for agent {decision.get('agent_id', 'unknown')} "
                f"requires commander review."
            )
            alert_id = self._alert_id([level, "autonomy", decision_id, message])
            alerts.append(
                {
                    "alert_id": alert_id,
                    "timestamp": str(decision.get("timestamp", _utcnow())),
                    "level": level,
                    "source_layer": "autonomy",
                    "title": "Human review required",
                    "message": message,
                    "action_url": "/dashboard/autonomy/decisions/review",
                }
            )
        return alerts

    def _build_system_alerts(self) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        jetson = self.system_provider.get_jetson_stats()
        gps = self.system_provider.get_gps_status()
        llm_status = self.system_provider._layer_status(  # pylint: disable=protected-access
            "src.llm_core.engine_registry", "EngineRegistry"
        )

        temperature = float(jetson.get("temperature_c", 0.0))
        if temperature >= 80.0:
            level = "CRITICAL" if temperature >= 90.0 else "HIGH"
            message = f"Jetson temperature is elevated at {temperature:.1f}C."
            alerts.append(
                {
                    "alert_id": self._alert_id([level, "system", "temperature", message]),
                    "timestamp": _utcnow(),
                    "level": level,
                    "source_layer": "system",
                    "title": "Thermal warning",
                    "message": message,
                    "action_url": "/dashboard/system/jetson",
                }
            )

        quality = str(gps.get("quality", "unknown")).upper()
        if quality in {"UNKNOWN", "DENIED", "NONE"}:
            message = f"GPS quality degraded ({quality}); localization confidence reduced."
            alerts.append(
                {
                    "alert_id": self._alert_id(["HIGH", "navigation", "gps", message]),
                    "timestamp": _utcnow(),
                    "level": "HIGH",
                    "source_layer": "navigation",
                    "title": "GPS quality degraded",
                    "message": message,
                    "action_url": "/dashboard/system/health",
                }
            )

        if llm_status.get("status") != "operational":
            message = "LLM core appears unavailable; routing may be degraded."
            alerts.append(
                {
                    "alert_id": self._alert_id(["MEDIUM", "llm_core", "engine", message]),
                    "timestamp": _utcnow(),
                    "level": "MEDIUM",
                    "source_layer": "llm_core",
                    "title": "Engine availability warning",
                    "message": message,
                    "action_url": "/dashboard/llm/status",
                }
            )

        return alerts

    def collect(self, level: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Collect, deduplicate, sort, and optionally filter active alerts."""
        safe_limit = max(1, min(int(limit), self.max_alerts))
        combined = self._build_threat_alerts() + self._build_review_alerts() + self._build_system_alerts()
        dedup: Dict[str, Dict[str, Any]] = {}
        for alert in combined:
            alert_id = str(alert.get("alert_id", "")).strip()
            if not alert_id or alert_id in self._dismissed:
                continue
            dedup[alert_id] = alert
        ordered = list(dedup.values())
        ordered.sort(
            key=lambda item: (
                _SEVERITY_ORDER.get(self._normalized_level(item.get("level")), 5),
                str(item.get("timestamp", "")),
            )
        )
        self._active = ordered[-self.max_alerts :]
        if level:
            target = self._normalized_level(level)
            return [a for a in self._active if self._normalized_level(a.get("level")) == target][:safe_limit]
        return self._active[:safe_limit]

    def get_alert_counts(self) -> Dict[str, int]:
        if not self._active:
            self.collect()
        counts = {"critical": 0, "high": 0, "medium": 0, "total": 0}
        for alert in self._active:
            level = self._normalized_level(alert.get("level")).lower()
            if level in counts:
                counts[level] += 1
            counts["total"] += 1
        return counts

    def dismiss(self, alert_id: str) -> None:
        if not isinstance(alert_id, str) or not alert_id.strip():
            return
        self._dismissed.add(alert_id)
        self._active = [a for a in self._active if str(a.get("alert_id")) != alert_id]

    def clear(self) -> None:
        self._active = []
        self._dismissed = set()

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "detail": f"active_alerts={len(self._active)}",
            "max_alerts": self.max_alerts,
        }
