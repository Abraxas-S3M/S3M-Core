"""Threat-to-LLM routing for S3M Layer 02 tactical assessments."""

from __future__ import annotations

from typing import List

from src.threat_detection.models import ThreatCategory, ThreatEvent


class ThreatClassifier:
    """Routes threat events to the most appropriate Layer 01 engine profile."""

    def __init__(self) -> None:
        self.available = False
        self._orchestrator = None
        self._query_request_cls = None
        try:
            from src.llm_core.engine_registry import TaskDomain
            from src.llm_core.orchestrator import Orchestrator, QueryRequest

            self._orchestrator = Orchestrator()
            self._query_request_cls = QueryRequest
            self._task_domain = TaskDomain
            self.available = True
        except Exception:
            self.available = False

    def _resolve_domain(self, category: ThreatCategory, consensus: bool = False):
        if not self.available:
            return None
        if consensus:
            return self._task_domain.CONSENSUS
        if category == ThreatCategory.CYBER:
            return self._task_domain.REASONING  # Grok
        if category == ThreatCategory.KINETIC:
            return self._task_domain.TACTICAL  # Phi-3
        if category == ThreatCategory.ELECTRONIC_WARFARE:
            return self._task_domain.REASONING  # Grok
        if category == ThreatCategory.SURVEILLANCE:
            return self._task_domain.PLANNING  # Mistral
        if category == ThreatCategory.HYBRID:
            return self._task_domain.CONSENSUS
        return self._task_domain.TACTICAL

    def classify(self, event: ThreatEvent) -> ThreatEvent:
        if not isinstance(event, ThreatEvent):
            raise ValueError("event must be a ThreatEvent")

        if not self.available or not self._orchestrator:
            event.llm_assessment = "[PENDING] LLM assessment unavailable — engines not loaded"
            return event

        require_consensus = event.category == ThreatCategory.HYBRID
        domain = self._resolve_domain(event.category, consensus=require_consensus)
        request = self._query_request_cls(
            prompt=event.to_prompt(),
            domain=domain,
            require_consensus=require_consensus,
        )
        try:
            response = self._orchestrator.process(request)
            if require_consensus and hasattr(response, "final_answer"):
                event.llm_assessment = str(response.final_answer)
            elif hasattr(response, "text"):
                event.llm_assessment = str(response.text)
            else:
                event.llm_assessment = "[PENDING] LLM response format unexpected"
        except Exception:
            event.llm_assessment = "[PENDING] LLM assessment unavailable — engines not loaded"
        return event

    def batch_classify(self, events: List[ThreatEvent]) -> List[ThreatEvent]:
        if not isinstance(events, list) or any(not isinstance(event, ThreatEvent) for event in events):
            raise ValueError("events must be a list of ThreatEvent")
        return [self.classify(event) for event in events]

    def generate_sitrep(self, events: List[ThreatEvent]) -> str:
        if not isinstance(events, list) or any(not isinstance(event, ThreatEvent) for event in events):
            raise ValueError("events must be a list of ThreatEvent")

        if not events:
            return "SITREP: No active threats detected."

        header = "S3M SITREP REQUEST\nClassification: UNCLASSIFIED\n"
        details = []
        for index, event in enumerate(events, start=1):
            details.append(
                (
                    f"{index}. [{event.level.name}/{event.category.value}] {event.title}\n"
                    f"   - Source: {event.source.value}\n"
                    f"   - Confidence: {event.confidence:.2f}\n"
                    f"   - Description: {event.description}"
                )
            )
        prompt = header + "\n".join(details) + "\nProvide concise military situation report with priorities."

        if not self.available or not self._orchestrator:
            return "[PENDING] LLM assessment unavailable — engines not loaded"

        request = self._query_request_cls(
            prompt=prompt,
            domain=self._resolve_domain(ThreatCategory.HYBRID, consensus=True),
            require_consensus=True,
        )
        try:
            response = self._orchestrator.process(request)
            if hasattr(response, "final_answer"):
                return str(response.final_answer)
            return "[PENDING] LLM response format unexpected"
        except Exception:
            return "[PENDING] LLM assessment unavailable — engines not loaded"
