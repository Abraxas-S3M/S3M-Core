"""Alert triage pipeline for converting ThreatEvents into SOC-ready artifacts."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from services.cyber.models import CaseSeverity, MITREMapping, Observable, ObservableType
from src.threat_detection.models import ThreatLevel


class AlertTriage:
    """Transforms Phase 5 threat events into Layer 07 triage records."""

    _IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    _DOMAIN_RE = re.compile(r"\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
    _MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
    _SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
    _URL_RE = re.compile(r"https?://[^\s]+")
    _EMAIL_RE = re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b")

    _SEVERITY_ORDER = {
        CaseSeverity.INFORMATIONAL: 1,
        CaseSeverity.LOW: 2,
        CaseSeverity.MEDIUM: 3,
        CaseSeverity.HIGH: 4,
        CaseSeverity.CRITICAL: 5,
    }

    def __init__(self, auto_case_threshold: CaseSeverity = CaseSeverity.MEDIUM) -> None:
        self.auto_case_threshold = CaseSeverity.from_value(auto_case_threshold)
        self._total_triaged = 0
        self._auto_cased = 0
        self._by_severity: Counter[str] = Counter()
        self._alert_queue: List[dict] = []

    def _severity_from_level(self, level: ThreatLevel) -> CaseSeverity:
        mapping = {
            ThreatLevel.CRITICAL: CaseSeverity.CRITICAL,
            ThreatLevel.HIGH: CaseSeverity.HIGH,
            ThreatLevel.MEDIUM: CaseSeverity.MEDIUM,
            ThreatLevel.LOW: CaseSeverity.LOW,
            ThreatLevel.INFO: CaseSeverity.INFORMATIONAL,
        }
        return mapping.get(level, CaseSeverity.INFORMATIONAL)

    def _severity_weight(self, severity: CaseSeverity) -> float:
        return {
            CaseSeverity.CRITICAL: 1.0,
            CaseSeverity.HIGH: 0.8,
            CaseSeverity.MEDIUM: 0.6,
            CaseSeverity.LOW: 0.35,
            CaseSeverity.INFORMATIONAL: 0.1,
        }[severity]

    def _auto_create_case(self, severity: CaseSeverity) -> bool:
        return self._SEVERITY_ORDER[severity] >= self._SEVERITY_ORDER[self.auto_case_threshold]

    def triage(self, event: Any) -> dict:
        """Triage one ThreatEvent into SOC case intake metadata."""
        from src.threat_detection.models import ThreatEvent

        if not isinstance(event, ThreatEvent):
            raise ValueError("event must be a ThreatEvent")

        observables = self.extract_observables(event.raw_data)
        severity = self._severity_from_level(event.level)
        mitre = MITREMapping.from_alert(event.category.value, event.description)
        has_mitre = 1.0 if mitre else 0.0
        observable_count = float(len(observables))

        triage_score = (
            self._severity_weight(severity) * 40.0
            + float(event.confidence) * 30.0
            + has_mitre * 15.0
            + observable_count * 15.0
        )
        triage_score = max(0.0, min(100.0, triage_score))
        auto_create = self._auto_create_case(severity)

        result = {
            "event_id": event.event_id,
            "severity": severity,
            "observables": observables,
            "mitre": mitre,
            "triage_score": round(triage_score, 3),
            "auto_create_case": auto_create,
        }

        self._total_triaged += 1
        self._by_severity[severity.value] += 1
        if auto_create:
            self._auto_cased += 1
        else:
            self._alert_queue.append(
                {
                    "event_id": event.event_id,
                    "severity": severity.value,
                    "score": round(triage_score, 3),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "title": event.title,
                    "description": event.description,
                }
            )
            if len(self._alert_queue) > 5000:
                del self._alert_queue[:-5000]
        return result

    def triage_batch(self, events: List[Any]) -> List[dict]:
        return [self.triage(event) for event in events]

    def extract_observables(self, raw_data: dict) -> List[Observable]:
        if not isinstance(raw_data, dict):
            return []
        # Convert nested payload to text for reliable regex extraction.
        text = json.dumps(raw_data, sort_keys=True)
        now = datetime.now(timezone.utc)
        values_seen: set[tuple[str, str]] = set()
        observables: List[Observable] = []

        def _append(kind: ObservableType, value: str) -> None:
            key = (kind.value, value)
            if key in values_seen:
                return
            values_seen.add(key)
            observables.append(
                Observable(
                    observable_id=str(uuid4()),
                    observable_type=kind,
                    value=value,
                    source_case_id="TRIAGE-PENDING",
                    first_seen=now,
                    last_seen=now,
                    tags=["triage_extracted"],
                    tlp="AMBER",
                    enrichments=[],
                )
            )

        for value in self._IPV4_RE.findall(text):
            _append(ObservableType.IP_ADDRESS, value)
        for value in self._SHA256_RE.findall(text):
            _append(ObservableType.FILE_HASH_SHA256, value)
        for value in self._MD5_RE.findall(text):
            _append(ObservableType.FILE_HASH_MD5, value)
        for value in self._URL_RE.findall(text):
            _append(ObservableType.URL, value.rstrip('",}'))
        for value in self._EMAIL_RE.findall(text):
            _append(ObservableType.EMAIL, value)
        for value in self._DOMAIN_RE.findall(text):
            lowered = value.lower()
            if lowered in {"localhost", "example.com", "json", "false", "true"}:
                continue
            if self._IPV4_RE.match(value):
                continue
            _append(ObservableType.DOMAIN, value)
        return observables

    def get_triage_stats(self) -> dict:
        return {
            "total_triaged": self._total_triaged,
            "by_severity": dict(self._by_severity),
            "auto_cased_count": self._auto_cased,
            "pending_alert_queue": len(self._alert_queue),
        }

    def get_alert_queue(self, severity: str | None = None, limit: int = 50) -> List[dict]:
        items = list(reversed(self._alert_queue))
        if severity:
            sev = severity.upper()
            items = [item for item in items if item.get("severity") == sev]
        safe_limit = max(1, min(int(limit), 500))
        return items[:safe_limit]
