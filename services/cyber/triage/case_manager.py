"""Thread-safe in-memory incident case manager for SOC operations."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.cyber.models import (
    CaseSeverity,
    CaseStatus,
    CaseVerdict,
    EnrichmentResult,
    IncidentCase,
    Observable,
)


class CaseManager:
    """Maintains SOC cases with bounded memory and auditable lifecycle updates."""

    def __init__(self, max_cases: int = 10000) -> None:
        if not isinstance(max_cases, int) or max_cases <= 0:
            raise ValueError("max_cases must be a positive integer")
        self.max_cases = max_cases
        self._cases: OrderedDict[str, IncidentCase] = OrderedDict()
        self._lock = Lock()

    def _ensure_capacity(self) -> None:
        while len(self._cases) > self.max_cases:
            self._cases.popitem(last=False)

    def create_case(
        self,
        title: str,
        description: str,
        severity: CaseSeverity,
        source_events: List[str],
        observables: Optional[List[dict]] = None,
        mitre_tactics: Optional[List[str]] = None,
        mitre_techniques: Optional[List[str]] = None,
    ) -> IncidentCase:
        with self._lock:
            case = IncidentCase(
                case_id=str(uuid4()),
                title=title,
                description=description,
                severity=CaseSeverity.from_value(severity),
                status=CaseStatus.NEW,
                source_events=list(source_events or []),
                observables=list(observables or []),
                mitre_tactics=list(mitre_tactics or []),
                mitre_techniques=list(mitre_techniques or []),
            )
            self._cases[case.case_id] = case
            self._ensure_capacity()
            return case

    def create_from_triage(self, triage_result: dict, event: Any) -> IncidentCase:
        if not isinstance(triage_result, dict):
            raise ValueError("triage_result must be a dict")
        observables = triage_result.get("observables", [])
        mitre = triage_result.get("mitre")
        case = self.create_case(
            title=f"SOC Case: {getattr(event, 'title', 'Threat Event')}",
            description=getattr(event, "description", "No description"),
            severity=triage_result.get("severity", CaseSeverity.LOW),
            source_events=[getattr(event, "event_id", "")],
            observables=[obs.to_dict() if hasattr(obs, "to_dict") else dict(obs) for obs in observables],
            mitre_tactics=[mitre.tactic_id] if mitre else [],
            mitre_techniques=[mitre.technique_id] if mitre else [],
        )
        case.add_timeline_entry("case_created_from_triage", "triage_engine", "Auto-created from triage result")
        return case

    def get_case(self, case_id: str) -> Optional[IncidentCase]:
        with self._lock:
            return self._cases.get(case_id)

    def update_case(self, case_id: str, **kwargs: Any) -> IncidentCase:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise ValueError(f"Case not found: {case_id}")
            for key, value in kwargs.items():
                if not hasattr(case, key):
                    continue
                if key == "severity":
                    value = CaseSeverity.from_value(value)
                elif key == "status":
                    value = CaseStatus.from_value(value)
                elif key == "verdict" and value is not None:
                    value = CaseVerdict.from_value(value)
                setattr(case, key, value)
                case.timeline.append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "case_updated",
                        "actor": "analyst",
                        "detail": f"{key} set to {value}",
                    }
                )
            case.updated_at = datetime.now(timezone.utc)
            return case

    def assign_analyst(self, case_id: str, analyst: str) -> IncidentCase:
        case = self.update_case(case_id, assigned_analyst=analyst, status=CaseStatus.IN_PROGRESS)
        case.add_timeline_entry("analyst_assigned", "soc_manager", f"Assigned to {analyst}")
        return case

    def escalate(self, case_id: str, reason: str) -> IncidentCase:
        case = self.update_case(case_id, status=CaseStatus.ESCALATED)
        case.add_timeline_entry("case_escalated", "soc_manager", reason)
        return case

    def resolve(self, case_id: str, verdict: CaseVerdict, resolution_notes: str) -> IncidentCase:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise ValueError(f"Case not found: {case_id}")
            case.verdict = CaseVerdict.from_value(verdict)
            case.status = CaseStatus.RESOLVED
            case.resolved_at = datetime.now(timezone.utc)
            case.updated_at = case.resolved_at
            case.add_timeline_entry("case_resolved", "soc_manager", resolution_notes)
            return case

    def close(self, case_id: str) -> IncidentCase:
        case = self.update_case(case_id, status=CaseStatus.CLOSED)
        case.add_timeline_entry("case_closed", "soc_manager", "Case closed after review")
        return case

    def reopen(self, case_id: str, reason: str) -> IncidentCase:
        case = self.update_case(case_id, status=CaseStatus.IN_PROGRESS, resolved_at=None)
        case.add_timeline_entry("case_reopened", "soc_manager", reason)
        return case

    def add_observable(self, case_id: str, observable: Observable) -> IncidentCase:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise ValueError(f"Case not found: {case_id}")
            case.observables.append(observable.to_dict())
            case.add_timeline_entry("observable_added", "soc_manager", observable.value)
            return case

    def add_enrichment(self, case_id: str, enrichment: EnrichmentResult) -> IncidentCase:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise ValueError(f"Case not found: {case_id}")
            case.enrichments.append(enrichment.to_dict())
            case.add_timeline_entry("enrichment_added", enrichment.analyzer, f"Verdict={enrichment.verdict}")
            return case

    def set_playbook(self, case_id: str, playbook_id: str) -> IncidentCase:
        case = self.update_case(case_id, playbook_id=playbook_id)
        case.add_timeline_entry("playbook_assigned", "soar_engine", playbook_id)
        return case

    def add_playbook_result(self, case_id: str, step_result: dict) -> IncidentCase:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise ValueError(f"Case not found: {case_id}")
            case.playbook_results.append(dict(step_result))
            case.add_timeline_entry("playbook_step_result", "soar_engine", f"step={step_result.get('step_id')}")
            return case

    def get_cases(
        self,
        status: str | None = None,
        severity: str | None = None,
        analyst: str | None = None,
        limit: int = 50,
    ) -> List[IncidentCase]:
        with self._lock:
            items = list(reversed(self._cases.values()))
            if status:
                status_enum = CaseStatus.from_value(status)
                items = [case for case in items if case.status == status_enum]
            if severity:
                severity_enum = CaseSeverity.from_value(severity)
                items = [case for case in items if case.severity == severity_enum]
            if analyst:
                items = [case for case in items if case.assigned_analyst == analyst]
            safe_limit = max(1, min(int(limit), 1000))
            return items[:safe_limit]

    def get_open_cases(self) -> List[IncidentCase]:
        with self._lock:
            return [case for case in self._cases.values() if case.is_open()]

    def get_stats(self) -> dict:
        with self._lock:
            cases = list(self._cases.values())
            by_status: Dict[str, int] = {}
            by_severity: Dict[str, int] = {}
            resolution_times: List[float] = []
            open_cases = [case for case in cases if case.is_open()]
            for case in cases:
                by_status[case.status.value] = by_status.get(case.status.value, 0) + 1
                by_severity[case.severity.value] = by_severity.get(case.severity.value, 0) + 1
                duration = case.duration_seconds()
                if duration is not None:
                    resolution_times.append(duration)
            mean_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0.0
            oldest_open: Optional[str] = None
            if open_cases:
                oldest_open = min(open_cases, key=lambda item: item.created_at).case_id
            return {
                "total": len(cases),
                "by_status": by_status,
                "by_severity": by_severity,
                "mean_resolution_time_seconds": round(mean_resolution, 3),
                "oldest_open_case_id": oldest_open,
            }

    def export(self, filepath: str) -> None:
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with self._lock:
            payload = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_cases": len(self._cases),
                "cases": [case.to_dict() for case in self._cases.values()],
            }
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
