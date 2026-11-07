"""SOC and escalation alerting for duress and coercion indicators."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.cyber.soc_manager import SOCManager
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


class ApprovalsSOCBridge:
    """Raise CRITICAL alerts without external API dependencies."""

    def __init__(self, escalation_list: Optional[List[str]] = None) -> None:
        self._soc = SOCManager()
        self.escalation_list = list(escalation_list or [])

    def raise_duress_alert(
        self,
        *,
        device_id: str,
        change_id: str,
        envelope_id: str,
    ) -> Dict[str, Any]:
        title = f"Duress PIN used on approver device {device_id}"
        event = ThreatEvent(
            source=ThreatSource.MANUAL,
            level=ThreatLevel.CRITICAL,
            category=ThreatCategory.CYBER,
            title=title,
            description=(
                f"Approver {device_id} entered duress PIN for change {change_id} "
                f"(envelope {envelope_id}). Treat as coercion; block device and "
                f"escalate to SOC immediately."
            ),
            raw_data={
                "device_id": device_id,
                "change_id": change_id,
                "envelope_id": envelope_id,
                "escalation_list": self.escalation_list,
            },
            confidence=1.0,
            classification="UNCLASSIFIED - FOUO",
        )
        result = self._soc.process_event(event)
        alert = {
            "severity": "CRITICAL",
            "title": title,
            "device_id": device_id,
            "change_id": change_id,
            "envelope_id": envelope_id,
            "soc_case_id": result.get("case_id"),
            "escalation_notified": list(self.escalation_list),
        }
        return alert
