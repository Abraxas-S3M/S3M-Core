"""Planning-engine output path: Le Chonk vLLM, legacy local GGUF, or labeled placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.integrations.lechonk.flags import rollback_planning_binding
from src.integrations.lechonk.planning_backend import LeChonkPlanningBackend
from src.integrations.lechonk.planning_factory import build_planning_backend
from src.integrations.lechonk.planning_gates import PlanningGateResult, evaluate_planning_gates
from src.integrations.lechonk.planning_schema import coa_options_from_text, planning_list_field
from src.quad_engine.local_llm import LocalLLMRunner
from src.quad_engine.models import OUTPUT_COA, EngineStatus, OperationalPacket, PLANNING_ENGINE

_PLANNING_OUTPUT_KEYS = frozenset(
    {"coa_options", "watch_priorities", "sensor_cueing", "commander_tasks"}
)


@dataclass
class PlanningGenerationContext:
    """Per-packet planning provenance for quad-engine audit."""

    output_origin: str = "placeholder"
    backing_engine_id: str = ""
    lechonk_attempted: bool = False
    lechonk_success: bool = False
    fallback_reason: str = ""
    schema_warnings: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    gates: Optional[PlanningGateResult] = None


@dataclass
class PlanningGenerateResult:
    value: Any
    status: EngineStatus
    context: PlanningGenerationContext


def _legacy_engine_id() -> str:
    return rollback_planning_binding()


def _legacy_fallback_text(output_key: str, packet: OperationalPacket, reason: str, placeholder_text: str) -> str:
    return (
        f"[LEGACY FALLBACK — not Le Chonk inference] reason={reason}; "
        f"output={output_key}; {placeholder_text}"
    )


def generate_planning_output(
    output_key: str,
    packet: OperationalPacket,
    *,
    local_llm: LocalLLMRunner,
    build_prompt: Callable[[str, OperationalPacket], str],
    build_placeholder: Callable[[str, OperationalPacket], Any],
    gates: Optional[PlanningGateResult] = None,
    planning_backend: Optional[LeChonkPlanningBackend] = None,
    engines_path: str = "configs/engines.yaml",
) -> PlanningGenerateResult:
    """Resolve planning output without masking fallback as live Le Chonk."""
    gates = gates or evaluate_planning_gates(engines_path=engines_path)
    ctx = PlanningGenerationContext(
        backing_engine_id=gates.routing.backing_engine_id or _legacy_engine_id(),
        gates=gates,
    )

    if output_key not in _PLANNING_OUTPUT_KEYS:
        value = build_placeholder(output_key, packet)
        ctx.output_origin = "placeholder"
        return PlanningGenerateResult(value, EngineStatus.PLACEHOLDER, ctx)

    if gates.may_use_lechonk:
        backend = planning_backend or build_planning_backend(engines_path=engines_path)
        if backend is None:
            gates = PlanningGateResult(
                may_use_lechonk=False,
                routing=gates.routing,
                rollback_engine_id=gates.rollback_engine_id,
                reasons=gates.reasons + ["vllm_base_url_unconfigured"],
            )
            ctx.gates = gates
        else:
            ctx.lechonk_attempted = True
            if not backend.load():
                ctx.fallback_reason = "backend_load_failed"
            else:
                health = backend.health_check()
                if not health.get("reachable"):
                    ctx.fallback_reason = str(health.get("reason") or "backend_unreachable")
                else:
                    prompt = build_prompt(output_key, packet)
                    out = backend.generate_planning(prompt, idempotency_key=packet.packet_id)
                    ctx.provenance = dict(out.get("provenance") or {})
                    if out.get("success"):
                        ctx.lechonk_success = True
                        ctx.output_origin = "lechonk_vllm"
                        ctx.backing_engine_id = gates.routing.backing_engine_id
                        text = str(out.get("text") or "")
                        if output_key == OUTPUT_COA:
                            value, warnings = coa_options_from_text(text, live=True)
                            ctx.schema_warnings = warnings
                            status = EngineStatus.LIVE_LOCAL
                            return PlanningGenerateResult(value, status, ctx)
                        if output_key in {"watch_priorities", "sensor_cueing", "commander_tasks"}:
                            value, warnings = planning_list_field(text, output_key)
                            if value:
                                ctx.schema_warnings = warnings
                                return PlanningGenerateResult(value, EngineStatus.LIVE_LOCAL, ctx)
                            ctx.schema_warnings = warnings + ["structured_field_fallback_to_text"]
                            return PlanningGenerateResult([text], EngineStatus.LIVE_LOCAL, ctx)
                        return PlanningGenerateResult(text, EngineStatus.LIVE_LOCAL, ctx)
                    ctx.fallback_reason = str(out.get("error") or "lechonk_generate_failed")

    # Legacy local GGUF on rollback engine binding (planning_engine registry entry).
    legacy_id = PLANNING_ENGINE
    if local_llm.engine_available(legacy_id):
        prompt = build_prompt(output_key, packet)
        text = local_llm.generate(legacy_id, prompt, system_prompt="")
        if text:
            ctx.output_origin = "legacy_local_gguf"
            ctx.backing_engine_id = _legacy_engine_id()
            if output_key == OUTPUT_COA:
                value, warnings = coa_options_from_text(text, live=False)
                ctx.schema_warnings = warnings
                return PlanningGenerateResult(value, EngineStatus.LIVE_LOCAL, ctx)
            return PlanningGenerateResult(text, EngineStatus.LIVE_LOCAL, ctx)

    placeholder = build_placeholder(output_key, packet)
    reason = ctx.fallback_reason or ";".join(gates.reasons[:3]) or "gates_closed"
    ctx.output_origin = "legacy_fallback_placeholder"
    ctx.fallback_reason = reason
    ctx.backing_engine_id = gates.rollback_engine_id
    if isinstance(placeholder, str):
        value: Any = _legacy_fallback_text(output_key, packet, reason, placeholder)
    elif isinstance(placeholder, list) and placeholder and isinstance(placeholder[0], dict):
        value = [
            {
                **item,
                "description": _legacy_fallback_text(
                    output_key, packet, reason, str(item.get("description", ""))
                ),
                "name": str(item.get("name", "Fallback COA")),
            }
            for item in placeholder
        ]
    elif isinstance(placeholder, list) and placeholder and isinstance(placeholder[0], str):
        value = [_legacy_fallback_text(output_key, packet, reason, item) for item in placeholder]
    else:
        value = placeholder
    return PlanningGenerateResult(value, EngineStatus.PLACEHOLDER, ctx)
