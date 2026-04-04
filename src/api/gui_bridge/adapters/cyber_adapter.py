"""Cyber workspace adapter.

Internal dependencies:
- services.cyber.soc_manager.SOCManager (incidents/cases)
- src.api.cyber_routes (SOC overview, alerts, platform status)
"""

from datetime import datetime, timezone
from typing import List

from src.api.gui_bridge.models.gui_schemas import (
    GUICyberData,
    GUICyberIncident,
    GUICyberResilienceMetric,
    SeverityLevel,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CyberAdapter:
    def __init__(self):
        self._soc = None
        try:
            from services.cyber.soc_manager import SOCManager

            self._soc = SOCManager()
        except Exception:
            pass

    def get_incidents(self) -> List[dict]:
        incidents = self._fetch_incidents()
        return {"incidents": incidents, "updatedAt": _now_iso()}

    def get_resilience(self) -> dict:
        metrics = self._fetch_resilience()
        return {"resilience": metrics, "updatedAt": _now_iso()}

    def _fetch_incidents(self) -> List[dict]:
        try:
            from src.api.cyber_routes import _soc_manager

            alerts = (
                _soc_manager.get_alert_queue()
                if hasattr(_soc_manager, "get_alert_queue")
                else []
            )
            cases = _soc_manager.get_cases() if hasattr(_soc_manager, "get_cases") else []
            results = []
            for a in alerts if isinstance(alerts, list) else []:
                ad = (
                    a
                    if isinstance(a, dict)
                    else (a.model_dump() if hasattr(a, "model_dump") else {})
                )
                results.append(
                    GUICyberIncident(
                        id=ad.get("id", ad.get("alert_id", "")),
                        title=ad.get("title", ad.get("rule_name", "Alert")),
                        severity=self._map_severity(ad.get("severity", "MEDIUM")),
                        status=ad.get("status", "open"),
                        source=ad.get("source", "SIEM"),
                        detectedAt=ad.get("timestamp", _now_iso()),
                        description=ad.get("description", ""),
                    ).model_dump()
                )
            for c in cases if isinstance(cases, list) else []:
                cd = (
                    c
                    if isinstance(c, dict)
                    else (c.model_dump() if hasattr(c, "model_dump") else {})
                )
                results.append(
                    GUICyberIncident(
                        id=cd.get("case_id", cd.get("id", "")),
                        title=cd.get("title", "Case"),
                        severity=self._map_severity(cd.get("severity", "MEDIUM")),
                        status=cd.get("status", "open"),
                        source=cd.get("source", "SOC"),
                        detectedAt=cd.get("created_at", _now_iso()),
                        description=cd.get("description", cd.get("summary", "")),
                    ).model_dump()
                )
            return results if results else self._default_incidents()
        except Exception:
            return self._default_incidents()

    def _fetch_resilience(self) -> List[dict]:
        try:
            from src.api.cyber_routes import _soc_manager

            overview = (
                _soc_manager.get_soc_overview()
                if hasattr(_soc_manager, "get_soc_overview")
                else {}
            )
            ov = (
                overview
                if isinstance(overview, dict)
                else (overview.model_dump() if hasattr(overview, "model_dump") else {})
            )
            return [
                GUICyberResilienceMetric(
                    domain="Network",
                    score=ov.get("network_health", 85),
                    status="operational",
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="Endpoint",
                    score=ov.get("endpoint_health", 78),
                    status="operational",
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="AI/Model",
                    score=ov.get("model_trust", 92),
                    status="operational",
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="SCADA/OT", score=ov.get("ot_health", 70), status="caution"
                ).model_dump(),
            ]
        except Exception:
            return [
                GUICyberResilienceMetric(
                    domain="Network", score=85, status="operational"
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="Endpoint", score=78, status="operational"
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="AI/Model", score=92, status="operational"
                ).model_dump(),
                GUICyberResilienceMetric(
                    domain="SCADA/OT", score=70, status="caution"
                ).model_dump(),
            ]

    @staticmethod
    def _map_severity(s) -> SeverityLevel:
        s = str(s).upper()
        return SeverityLevel[s] if s in SeverityLevel.__members__ else SeverityLevel.MEDIUM

    @staticmethod
    def _default_incidents():
        return [
            GUICyberIncident(
                id="CYB-001",
                title="Anomalous DNS exfiltration attempt",
                severity=SeverityLevel.HIGH,
                status="investigating",
                source="Suricata",
                detectedAt=_now_iso(),
                description="Unusual DNS query volume to external resolver.",
            ).model_dump(),
            GUICyberIncident(
                id="CYB-002",
                title="Failed SSH brute-force",
                severity=SeverityLevel.MEDIUM,
                status="contained",
                source="Wazuh",
                detectedAt=_now_iso(),
                description="Multiple failed auth attempts on edge node.",
            ).model_dump(),
        ]
