"""All-in gating before planning_engine may call Le Chonk (fail-closed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.cortex.model_admission import ModelAdmissionGate, is_engine_routable
from src.integrations.lechonk.flags import (
    BACKING_ENGINE_ID,
    execution_allowed_by_manifest,
    lechonk_enabled,
    load_lechonk_manifest,
    rollback_planning_binding,
)
from src.integrations.lechonk.hardware import collect_hardware_snapshot
from src.integrations.lechonk.orchestrator_routing import PlanningRoutingDecision, resolve_planning_backing_engine
from src.integrations.lechonk.runtime_compat import evaluate_runtime_compatibility
from src.integrations.lechonk.scheduler import select_deployment_profile


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PlanningGateResult:
    may_use_lechonk: bool
    routing: PlanningRoutingDecision
    rollback_engine_id: str
    reasons: List[str] = field(default_factory=list)
    profile: str = ""
    runtime_ready: bool = False
    security_blocked: bool = False

    def audit_record(self) -> Dict[str, Any]:
        return {
            "may_use_lechonk": self.may_use_lechonk,
            "reasons": list(self.reasons),
            "profile": self.profile,
            "runtime_ready": self.runtime_ready,
            "security_blocked": self.security_blocked,
            "routing": self.routing.audit_record(),
        }


def evaluate_planning_gates(
    *,
    engines_path: str = "configs/engines.yaml",
    gate: Optional[ModelAdmissionGate] = None,
) -> PlanningGateResult:
    """Aggregate feature flag, admission, runtime, hardware, and security checks."""
    gate = gate or ModelAdmissionGate(engines_path=engines_path)
    rollback = rollback_planning_binding()
    routing = resolve_planning_backing_engine(engines_path=engines_path, gate=gate)
    reasons: List[str] = []

    if not lechonk_enabled():
        reasons.append("feature_or_manifest_execution_blocked")
        return PlanningGateResult(
            may_use_lechonk=False,
            routing=routing,
            rollback_engine_id=rollback,
            reasons=reasons,
            security_blocked=True,
        )

    doc = load_lechonk_manifest()
    security = doc.get("security") or {}
    if not execution_allowed_by_manifest():
        reasons.append("manifest_execution_disabled")
        return PlanningGateResult(
            may_use_lechonk=False,
            routing=routing,
            rollback_engine_id=rollback,
            reasons=reasons,
            security_blocked=True,
        )
    if isinstance(security, dict):
        if security.get("preserve_quarantine") and str(doc.get("status", "")).lower() == "quarantine":
            reasons.append("model_quarantined")
        if security.get("require_signed_admission") and not str((doc.get("admission") or {}).get("signature")):
            reasons.append("unsigned_model_manifest")
        if security.get("require_runtime_evaluation"):
            pass

    runtime = evaluate_runtime_compatibility(
        lab_smoke_test_passed=_env_truthy("S3M_LECHONK_RUNTIME_SMOKE_PASSED"),
    )
    selection = select_deployment_profile(doc, force_fallback=False)
    if not routing.used_lechonk:
        reasons.append(routing.fallback_reason or "routing_fallback")
    if not is_engine_routable(BACKING_ENGINE_ID, engines_path):
        reasons.append("engine_not_routable")
    decision = gate.evaluate(BACKING_ENGINE_ID, production=True)
    if not decision.allowed:
        reasons.extend(decision.reasons[:5])

    if not runtime.ready_for_inference:
        reasons.append("runtime_smoke_not_passed")

    if not selection.uses_lechonk_weights():
        reasons.extend(selection.rejected[:3] or ["no_eligible_deployment_profile"])

    may_use = (
        routing.used_lechonk
        and runtime.ready_for_inference
        and selection.uses_lechonk_weights()
        and len(reasons) == 0
    )
    return PlanningGateResult(
        may_use_lechonk=may_use,
        routing=routing,
        rollback_engine_id=rollback,
        reasons=reasons,
        profile=selection.selected.value,
        runtime_ready=runtime.ready_for_inference,
        security_blocked=any(r.startswith("unsigned") or "quarantine" in r for r in reasons),
    )
