"""Resolve which physical engine backs the planning_engine logical role."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.cortex.model_admission import ModelAdmissionGate, is_engine_routable, quad_engine_bindings
from src.integrations.lechonk.flags import BACKING_ENGINE_ID, lechonk_enabled, rollback_planning_binding


@dataclass(frozen=True)
class PlanningRoutingDecision:
    logical_engine_id: str
    backing_engine_id: str
    used_lechonk: bool
    fallback_reason: str

    def audit_record(self) -> dict:
        return {
            "logical_engine": self.logical_engine_id,
            "backing_engine": self.backing_engine_id,
            "lechonk": self.used_lechonk,
            "fallback_reason": self.fallback_reason,
        }


def configured_planning_binding(engines_path: str = "configs/engines.yaml") -> str:
    bindings = quad_engine_bindings(engines_path)
    return str(bindings.get("planning_engine") or rollback_planning_binding())


def resolve_planning_backing_engine(
    *,
    engines_path: str = "configs/engines.yaml",
    gate: Optional[ModelAdmissionGate] = None,
) -> PlanningRoutingDecision:
    """
    Production routing stays on legacy mistral until flag + admission + routable engine.

    Feature flag defaults false; manifest keeps execution disabled.
    """
    logical = "planning_engine"
    rollback = rollback_planning_binding()
    yaml_binding = configured_planning_binding(engines_path)

    if not lechonk_enabled():
        reason = "feature_disabled_or_manifest_execution_blocked"
        backing = yaml_binding if yaml_binding else rollback
        return PlanningRoutingDecision(
            logical_engine_id=logical,
            backing_engine_id=backing,
            used_lechonk=False,
            fallback_reason=reason,
        )

    gate = gate or ModelAdmissionGate(engines_path=engines_path)
    if not is_engine_routable(BACKING_ENGINE_ID, engines_path):
        return PlanningRoutingDecision(
            logical_engine_id=logical,
            backing_engine_id=rollback,
            used_lechonk=False,
            fallback_reason="lechonk_not_routable",
        )

    decision = gate.evaluate(BACKING_ENGINE_ID, production=True)
    if not decision.allowed:
        return PlanningRoutingDecision(
            logical_engine_id=logical,
            backing_engine_id=rollback,
            used_lechonk=False,
            fallback_reason="admission_denied:" + ";".join(decision.reasons[:3]),
        )

    return PlanningRoutingDecision(
        logical_engine_id=logical,
        backing_engine_id=BACKING_ENGINE_ID,
        used_lechonk=True,
        fallback_reason="",
    )
