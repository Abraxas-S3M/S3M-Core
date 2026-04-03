"""
CPU-first model execution planner for denied edge nodes.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from src.edge_runtime.degradation_controller import DegradationController, OperatingMode
from src.edge_runtime.hardware_profiler import NodeProfile


class Precision(str, Enum):
    INT4 = "int4"
    INT8 = "int8"
    FP16 = "fp16"
    FP32 = "fp32"


class ExecutionDecision(str, Enum):
    RUN_LOCAL = "run_local"
    DEFER_TO_PEER = "defer_to_peer"
    SUMMARIZE_INSTEAD = "summarize_instead"
    REJECT = "reject"


@dataclass(frozen=True)
class ModelVariant:
    model_id: str
    variant_tag: str
    precision: Precision
    file_path: str
    size_mb: float
    min_ram_gb: float
    requires_gpu: bool
    max_context: int
    estimated_tps_cpu: float
    estimated_tps_gpu: float


DEFAULT_VARIANTS: List[ModelVariant] = [
    ModelVariant("phi3-mini", "q4_k_m", Precision.INT4, "models/phi3-mini-q4_k_m.gguf", 2200.0, 3.0, False, 4096, 16.0, 45.0),
    ModelVariant("mistral-7b", "q4_k_m", Precision.INT4, "models/mistral-7b-q4_k_m.gguf", 4100.0, 5.0, False, 4096, 8.0, 28.0),
    ModelVariant("grok-8b", "q4_k_m", Precision.INT4, "models/grok-8b-q4_k_m.gguf", 4600.0, 6.0, False, 4096, 6.0, 22.0),
    ModelVariant("allam-7b", "q4_k_m", Precision.INT4, "models/allam-7b-q4_k_m.gguf", 4100.0, 5.0, False, 4096, 7.0, 26.0),
    ModelVariant("phi3-mini", "q8_0", Precision.INT8, "models/phi3-mini-q8_0.gguf", 3200.0, 4.0, False, 4096, 11.0, 38.0),
    ModelVariant("mistral-7b", "q8_0", Precision.INT8, "models/mistral-7b-q8_0.gguf", 6200.0, 8.0, False, 4096, 5.0, 20.0),
    ModelVariant("phi3-mini", "fp16", Precision.FP16, "models/phi3-mini-fp16.gguf", 4200.0, 6.0, True, 8192, 3.0, 52.0),
    ModelVariant("mistral-7b", "fp16", Precision.FP16, "models/mistral-7b-fp16.gguf", 12800.0, 16.0, True, 8192, 1.2, 30.0),
]


@dataclass
class ExecutionPlan:
    decision: ExecutionDecision
    variant: Optional[ModelVariant]
    precision: Precision
    max_tokens: int
    max_context: int
    max_batch: int
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "decision": self.decision.value,
            "model_id": self.variant.model_id if self.variant else None,
            "variant_tag": self.variant.variant_tag if self.variant else None,
            "precision": self.precision.value,
            "max_tokens": self.max_tokens,
            "max_context": self.max_context,
            "max_batch": self.max_batch,
            "reason": self.reason,
        }


class ModelExecutionPlanner:
    """Selects lowest-footprint viable model variant per current operating mode."""

    def __init__(
        self,
        profile: NodeProfile,
        controller: DegradationController,
        variants: Optional[List[ModelVariant]] = None,
    ) -> None:
        self.profile = profile
        self.controller = controller
        self.variants = list(variants) if variants is not None else list(DEFAULT_VARIANTS)

    def plan(self, model_id: str, requested_tokens: int = 512) -> ExecutionPlan:
        mode = self.controller.current_mode
        policy = self.controller.current_policy()
        candidates = [variant for variant in self.variants if variant.model_id == model_id]
        if not candidates:
            return ExecutionPlan(
                decision=ExecutionDecision.REJECT,
                variant=None,
                precision=Precision.INT4,
                max_tokens=0,
                max_context=0,
                max_batch=0,
                reason=f"Unknown model_id: {model_id}",
            )

        feasible: List[ModelVariant] = []
        for variant in candidates:
            if variant.requires_gpu and (not policy.allow_gpu or not self.profile.gpu_detected):
                continue
            if variant.min_ram_gb > self.profile.ram_available_gb:
                continue
            feasible.append(variant)

        if not feasible:
            if policy.allow_external_inference:
                return ExecutionPlan(
                    decision=ExecutionDecision.DEFER_TO_PEER,
                    variant=None,
                    precision=Precision.INT4,
                    max_tokens=0,
                    max_context=0,
                    max_batch=0,
                    reason="No local variant fits current resource envelope; defer to peer.",
                )
            return ExecutionPlan(
                decision=ExecutionDecision.SUMMARIZE_INSTEAD,
                variant=None,
                precision=Precision.INT4,
                max_tokens=0,
                max_context=0,
                max_batch=0,
                reason="No local variant fits and external inference is disabled.",
            )

        chosen = sorted(feasible, key=lambda item: item.size_mb)[0]
        if mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL:
            token_cap = min(256, chosen.max_context)
        elif mode == OperatingMode.MODE_B_CPU_CONSTRAINED:
            token_cap = min(512, chosen.max_context)
        else:
            token_cap = chosen.max_context

        max_tokens = max(1, min(int(requested_tokens), token_cap))
        max_context = chosen.max_context
        if mode in {OperatingMode.MODE_B_CPU_CONSTRAINED, OperatingMode.MODE_D_OFFLINE_SURVIVAL}:
            max_context = min(max_context, 2048)
        max_batch = 4 if mode == OperatingMode.MODE_A_FULL_EDGE else 1

        return ExecutionPlan(
            decision=ExecutionDecision.RUN_LOCAL,
            variant=chosen,
            precision=chosen.precision,
            max_tokens=max_tokens,
            max_context=max_context,
            max_batch=max_batch,
            reason=f"Selected smallest feasible variant under {mode.value} policy.",
        )
