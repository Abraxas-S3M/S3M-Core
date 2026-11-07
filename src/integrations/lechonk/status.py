"""Operational readiness vocabulary for Le Chonk (truthful, GUI-safe)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.cortex.model_admission import ModelAdmissionGate, is_engine_routable
from src.integrations.lechonk.flags import BACKING_ENGINE_ID, execution_allowed_by_manifest, lechonk_enabled, rollback_planning_binding
from src.integrations.lechonk.runtime_compat import evaluate_runtime_compatibility
from src.integrations.lechonk.scheduler import select_deployment_profile


class ReadinessPhase(str, Enum):
    QUARANTINED = "quarantined"
    REGISTERED = "registered"
    ADMITTED = "admitted"
    WEIGHTS_PRESENT = "weights_present"
    BACKEND_HEALTHY = "backend_healthy"
    MODEL_LOADED = "model_loaded"
    INFERENCE_VERIFIED = "inference_verified"
    UNAVAILABLE = "unavailable"
    FALLBACK = "fallback"


@dataclass
class PlanningBackendReadiness:
    """Extended status for planning_engine without replacing legacy EngineStatus."""

    backing_engine_id: str
    phase: ReadinessPhase
    precision: str = ""
    revision: str = ""
    runtime: str = ""
    device: str = ""
    feature_flag_enabled: bool = False
    execution_allowed: bool = False
    routable: bool = False
    fallback_engine_id: str = ""
    fallback_reason: str = ""
    profile: str = ""
    notes: List[str] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "backing_engine_id": self.backing_engine_id,
            "phase": self.phase.value,
            "precision": self.precision,
            "revision": self.revision,
            "runtime": self.runtime,
            "device": self.device,
            "feature_flag_enabled": self.feature_flag_enabled,
            "execution_allowed": self.execution_allowed,
            "routable": self.routable,
            "fallback_engine_id": self.fallback_engine_id,
            "fallback_reason": self.fallback_reason,
            "profile": self.profile,
            "notes": list(self.notes),
            "last_updated": self.last_updated,
        }


def compute_planning_readiness(
    gate: Optional[ModelAdmissionGate] = None,
    *,
    engines_path: str = "configs/engines.yaml",
) -> PlanningBackendReadiness:
    gate = gate or ModelAdmissionGate(engines_path=engines_path)
    flag_on = lechonk_enabled()
    exec_ok = execution_allowed_by_manifest()
    routable = is_engine_routable(BACKING_ENGINE_ID, engines_path)
    decision = gate.evaluate(BACKING_ENGINE_ID, production=True)
    runtime = evaluate_runtime_compatibility()
    selection = select_deployment_profile(force_fallback=not flag_on)
    rollback = rollback_planning_binding()

    phase = ReadinessPhase.QUARANTINED
    notes: List[str] = []
    fallback_reason = ""

    if not flag_on:
        phase = ReadinessPhase.FALLBACK
        fallback_reason = "S3M_LECHONK_ENABLED false or execution disallowed by manifest"
    elif not exec_ok:
        phase = ReadinessPhase.QUARANTINED
        notes.append("manifest execution_enabled=false")
    elif not decision.allowed:
        phase = ReadinessPhase.QUARANTINED
        notes.extend(decision.reasons[:5])
    elif decision.allowed and routable:
        phase = ReadinessPhase.ADMITTED
    else:
        phase = ReadinessPhase.REGISTERED

    if flag_on and not runtime.ready_for_inference:
        phase = ReadinessPhase.UNAVAILABLE
        notes.append("runtime_smoke_test_not_passed")

    profile = selection.selected.value
    return PlanningBackendReadiness(
        backing_engine_id=BACKING_ENGINE_ID if flag_on and decision.allowed else rollback,
        phase=phase,
        precision=profile if selection.uses_lechonk_weights() else "",
        revision="",
        runtime=runtime.runtime,
        device="gpu" if selection.uses_lechonk_weights() else "cpu",
        feature_flag_enabled=flag_on,
        execution_allowed=exec_ok,
        routable=routable and decision.allowed,
        fallback_engine_id=rollback,
        fallback_reason=fallback_reason,
        profile=profile,
        notes=notes,
    )
