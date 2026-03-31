"""Threat hunting module orchestrating correlation, escalation, and OSINT."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.apps._shared import utc_now_iso
from src.apps.threat_hunting.escalation_manager import EscalationManager
from src.apps.threat_hunting.osint_fuser import OSINTFuser
from src.apps.threat_hunting.threat_correlator import ThreatCorrelator
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest
from src.threat_detection.threat_manager import ThreatManager


class ThreatHuntingModule:
    """Vertical threat hunting workflow for mission operations."""

    def __init__(self) -> None:
        self.correlator = ThreatCorrelator()
        self.osint = OSINTFuser()
        self.escalation = EscalationManager()
        self.threat_manager = ThreatManager()
        self.orchestrator = Orchestrator()

    def hunt(self, events: Optional[List[dict]] = None) -> dict:
        if events is None:
            events = [event.to_dict() for event in self.threat_manager.get_threats(limit=200)]
        correlations = self.correlator.correlate(events)
        escalations = self.escalation.evaluate_batch(correlations)
        summary = (
            f"Correlations: {len(correlations)}; escalations: {len(escalations)}; "
            f"window: {self.correlator.time_window_seconds}s."
        )
        return {"correlations": correlations, "escalations": escalations, "summary": summary}

    def analyze_osint(self, query: str, files: Optional[List[str]] = None) -> dict:
        return self.osint.analyze(query, context_files=files)

    def get_threat_landscape(self) -> dict:
        recent = [event.to_dict() for event in self.threat_manager.get_threats(limit=100)]
        correlations = self.correlator.correlate(recent)
        active = self.escalation.get_active_escalations()
        osint_stats = self.osint.get_stats()

        prompt = (
            "Summarize current tactical threat landscape in one paragraph. "
            f"Recent threats={len(recent)}, correlations={len(correlations)}, "
            f"active escalations={len(active)}, osint={osint_stats}."
        )
        response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
        summary = response.text if hasattr(response, "text") else "Threat landscape summary unavailable."
        if "pending" in summary.lower():
            summary = (
                f"Threat landscape: {len(recent)} recent threats, {len(correlations)} correlations, "
                f"{len(active)} active escalations. Continue ISR and cyber monitoring."
            )

        return {
            "recent_threats": recent,
            "correlations": correlations,
            "active_escalations": active,
            "osint_stats": osint_stats,
            "summary": summary,
            "timestamp": utc_now_iso(),
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "correlator_patterns": self.correlator.get_patterns(),
            "osint": self.osint.get_stats(),
            "rules": len(self.escalation.get_rules()),
            "timestamp": utc_now_iso(),
        }

