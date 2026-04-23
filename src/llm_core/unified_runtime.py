"""
Top-level unified quad-engine runtime coordinator for S3M.

This module executes the full 10-step mission pipeline from request ingestion
to authoritative decision, state persistence, and audit-ready output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .engine_output import StructuredEngineOutput
from .engine_registry import DOMAIN_ROUTING, EngineID, TaskDomain
from .engine_runtime import EngineRuntimeAdapter
from .reconciliation_engine import ReconciliationEngine
from .shared_state import MissionContext, MissionState


class RuntimeMode(str, Enum):
    """Execution mode controlling engine routing policy."""

    DOMAIN = "domain"
    CONSENSUS = "consensus"
    EXPLICIT = "explicit"


@dataclass(slots=True)
class MissionRequest:
    """Mission request payload for unified runtime execution."""

    prompt: str
    mission_type: str = "general"
    mission_id: str = field(default_factory=lambda: f"mission-{uuid4().hex[:12]}")
    rules_of_engagement: str = "weapons_hold"
    consensus_mode: bool = False
    explicit_engines: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    timeout_seconds: float = 20.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable request payload."""
        return {
            "prompt": self.prompt,
            "mission_type": self.mission_type,
            "mission_id": self.mission_id,
            "rules_of_engagement": self.rules_of_engagement,
            "consensus_mode": self.consensus_mode,
            "explicit_engines": list(self.explicit_engines or []),
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class MissionResult:
    """Unified runtime result artifact with decision, state, and audit context."""

    mission_id: str
    task_id: str
    selected_engines: List[str]
    structured_outputs: Dict[str, Dict[str, Any]]
    decision: Dict[str, Any]
    state_snapshot: Dict[str, Any]
    runtime_mode: str
    audit_log: List[Dict[str, Any]]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable mission result."""
        return {
            "mission_id": self.mission_id,
            "task_id": self.task_id,
            "selected_engines": list(self.selected_engines),
            "structured_outputs": dict(self.structured_outputs),
            "decision": dict(self.decision),
            "state_snapshot": dict(self.state_snapshot),
            "runtime_mode": self.runtime_mode,
            "audit_log": list(self.audit_log),
            "created_at": self.created_at,
        }


class UnifiedRuntime:
    """
    Unified runtime executing synchronized quad-engine mission workflow.

    10-step mission pipeline:
      1) Ingest request
      2) Build mission context
      3) Route engines
      4) Execute engines live
      5) Collect structured outputs
      6) Write outputs to shared state
      7) Reconcile conflicts
      8) Produce authoritative decision
      9) Persist audit trail
      10) Return mission result
    """

    def __init__(
        self,
        *,
        runtime_adapter: Optional[EngineRuntimeAdapter] = None,
        reconciliation: Optional[ReconciliationEngine] = None,
    ) -> None:
        self.runtime_adapter = runtime_adapter or EngineRuntimeAdapter()
        self.reconciliation = reconciliation or ReconciliationEngine()

    def execute_mission(self, request: MissionRequest) -> MissionResult:
        """Execute full mission pipeline and return structured result."""
        audit: List[Dict[str, Any]] = []
        task_id = f"task-{uuid4().hex[:8]}"

        # 1) Ingest request
        safe_prompt = (request.prompt or "").strip() or "status check"
        audit.append(self._audit_event("request_ingested", {"task_id": task_id}))

        # 2) Build context + state
        state = MissionState()
        context = MissionContext(
            mission_id=request.mission_id,
            mission_type=request.mission_type,
            rules_of_engagement=request.rules_of_engagement,
            metadata={"request_metadata": dict(request.metadata)},
        )
        state.set_context(context)
        audit.append(
            self._audit_event(
                "context_built",
                {
                    "mission_id": request.mission_id,
                    "mission_type": request.mission_type,
                    "roe": request.rules_of_engagement,
                },
            )
        )

        # 3) Route engines
        selected_ids, mode = self._route_engines(request=request, prompt=safe_prompt)
        selected = [item.value for item in selected_ids]
        audit.append(
            self._audit_event(
                "engines_routed",
                {"runtime_mode": mode.value, "selected_engines": selected},
            )
        )

        # 4) Execute LIVE
        outputs = self.runtime_adapter.execute_engines(
            engine_ids=selected_ids,
            prompt=safe_prompt,
            task_id=task_id,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
        )
        audit.append(
            self._audit_event(
                "engines_executed_live",
                {"engines_executed": len(outputs), "task_id": task_id},
            )
        )

        # 5) Collect structured outputs
        structured_outputs: Dict[str, StructuredEngineOutput] = {}
        for key, output in outputs.items():
            engine_key = key.value if isinstance(key, EngineID) else str(key)
            structured_outputs[engine_key] = output
        audit.append(
            self._audit_event(
                "structured_outputs_collected",
                {"outputs_collected": len(structured_outputs)},
            )
        )

        # 6) Write to shared state
        for output in structured_outputs.values():
            state.ingest_engine_output(output)
        audit.append(
            self._audit_event(
                "state_updated",
                {"state_version": state.version, "contribution_count": len(structured_outputs)},
            )
        )

        # 7-8) Reconcile + decision synthesis
        decision = self.reconciliation.reconcile(
            structured_outputs,
            state,
            ingest_outputs=False,
        )
        audit.append(
            self._audit_event(
                "decision_synthesized",
                {
                    "decision_id": decision.decision_id,
                    "review_status": decision.review_status,
                    "confidence": decision.confidence,
                },
            )
        )

        # 9) Persist audit (in-memory for air-gap compatibility)
        snapshot = state.snapshot()
        audit.append(
            self._audit_event(
                "audit_persisted",
                {"snapshot_version": snapshot.get("version"), "events": len(audit) + 1},
            )
        )

        # 10) Return result
        return MissionResult(
            mission_id=request.mission_id,
            task_id=task_id,
            selected_engines=selected,
            structured_outputs={
                engine_id: output.to_dict()
                for engine_id, output in structured_outputs.items()
            },
            decision=decision.to_dict(),
            state_snapshot=snapshot,
            runtime_mode=mode.value,
            audit_log=audit,
        )

    def _route_engines(
        self,
        *,
        request: MissionRequest,
        prompt: str,
    ) -> tuple[List[EngineID], RuntimeMode]:
        """Route engines by explicit override, consensus mode, or domain mapping."""
        if request.explicit_engines:
            parsed = [self._to_engine_id(item) for item in request.explicit_engines]
            selected = [item for item in parsed if item is not None]
            if selected:
                return selected, RuntimeMode.EXPLICIT

        if request.consensus_mode:
            return list(EngineID), RuntimeMode.CONSENSUS

        domain = self._classify_domain(prompt=prompt, mission_type=request.mission_type)
        primary = DOMAIN_ROUTING.get(domain, EngineID.PHI3)
        # Tactical context: include one backup engine for degraded resilience.
        backup = EngineID.MISTRAL if primary != EngineID.MISTRAL else EngineID.GROK
        return [primary, backup], RuntimeMode.DOMAIN

    @staticmethod
    def _to_engine_id(value: str) -> Optional[EngineID]:
        """Convert string identifier into EngineID."""
        for engine_id in EngineID:
            if value == engine_id.value:
                return engine_id
        return None

    @staticmethod
    def _classify_domain(*, prompt: str, mission_type: str) -> TaskDomain:
        """Classify mission domain from prompt and mission type hints."""
        text = f"{mission_type} {prompt}".lower()
        if any(token in text for token in ("arabic", "عربي", "ترجمة", "التهديد")):
            return TaskDomain.ARABIC_NLP
        if any(token in text for token in ("analyze", "assess", "reason", "evaluate", "implication")):
            return TaskDomain.REASONING
        if any(token in text for token in ("plan", "route", "timeline", "logistics", "allocate")):
            return TaskDomain.PLANNING
        return TaskDomain.TACTICAL

    @staticmethod
    def _audit_event(event_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Create one mission audit event record."""
        return {
            "event_type": event_type,
            "details": dict(details),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
