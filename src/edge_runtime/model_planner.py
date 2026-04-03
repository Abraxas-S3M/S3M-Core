"""
CPU-first model execution planner.
For each workload, chooses: which model variant, precision, context limits,
and whether to run locally, defer, or summarize instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.edge_runtime.degradation_controller import (
    DegradationController,
    ModePolicy,
    OperatingMode,
)
from src.edge_runtime.hardware_profiler import NodeProfile

logger = logging.getLogger("s3m.edge_runtime.model_planner")


class Precision(Enum):
    INT4 = "int4"  # Q4_K_M — CPU austere baseline
    INT8 = "int8"  # Q8 — CPU standard
    FP16 = "fp16"  # GPU required
    FP32 = "fp32"  # Debug / server only


class ExecutionDecision(Enum):
    RUN_LOCAL = "run_local"
    DEFER_TO_PEER = "defer_to_peer"
    SUMMARIZE_INSTEAD = "summarize_instead"
    REJECT = "reject"


@dataclass(frozen=True)
class ModelVariant:
    """One quantized variant of a model available for selection."""

    model_id: str  # e.g. "phi3-mini"
    variant_tag: str  # e.g. "q4_k_m", "q8_0", "fp16"
    precision: Precision
    file_path: str
    size_mb: float
    min_ram_gb: float
    requires_gpu: bool
    max_context: int
    estimated_tps_cpu: float  # tokens/sec on reference CPU
    estimated_tps_gpu: float  # tokens/sec on reference GPU


# ── Default variant catalog (extends engine_registry.py) ─────
DEFAULT_VARIANTS: List[ModelVariant] = [
    ModelVariant(
        "phi3-mini",
        "q4_k_m",
        Precision.INT4,
        "models/phi3/phi-3-mini-4k-instruct-q4_k_m.gguf",
        2200,
        3.0,
        False,
        4096,
        12.0,
        45.0,
    ),
    ModelVariant(
        "phi3-mini",
        "q8_0",
        Precision.INT8,
        "models/phi3/phi-3-mini-4k-instruct-q8_0.gguf",
        4000,
        5.0,
        False,
        4096,
        8.0,
        40.0,
    ),
    ModelVariant(
        "mistral-7b",
        "q4_k_m",
        Precision.INT4,
        "models/mistral/mistral-7b-instruct-v0.3-q4_k_m.gguf",
        4100,
        5.0,
        False,
        8192,
        6.0,
        35.0,
    ),
    ModelVariant(
        "mistral-7b",
        "fp16",
        Precision.FP16,
        "models/mistral/mistral-7b-instruct-v0.3-fp16.gguf",
        14000,
        16.0,
        True,
        32768,
        0.5,
        55.0,
    ),
    ModelVariant(
        "grok-8b",
        "q4_k_m",
        Precision.INT4,
        "models/grok/grok-8b-q4_k_m.gguf",
        4600,
        6.0,
        False,
        8192,
        5.0,
        30.0,
    ),
    ModelVariant(
        "allam-7b",
        "q4_k_m",
        Precision.INT4,
        "models/allam/allam-7b-q4_k_m.gguf",
        4100,
        5.0,
        False,
        4096,
        5.5,
        32.0,
    ),
]


@dataclass(frozen=True)
class ExecutionPlan:
    decision: ExecutionDecision
    variant: Optional[ModelVariant]
    precision: Precision
    max_tokens: int
    max_context: int
    max_batch: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "variant": self.variant.variant_tag if self.variant else None,
            "model_id": self.variant.model_id if self.variant else None,
            "precision": self.precision.value,
            "max_tokens": self.max_tokens,
            "max_context": self.max_context,
            "max_batch": self.max_batch,
            "reason": self.reason,
        }


class ModelExecutionPlanner:
    """
    Given a workload request, selects the best model variant that
    fits within current hardware and degradation constraints.
    CPU is the baseline, not the fallback.
    """

    def __init__(
        self,
        profile: NodeProfile,
        controller: DegradationController,
        variants: Optional[List[ModelVariant]] = None,
    ) -> None:
        self.profile = profile
        self.controller = controller
        self.variants = variants or DEFAULT_VARIANTS
        self._loaded_mb: float = 0.0

    def plan(self, model_id: str, requested_tokens: int = 512) -> ExecutionPlan:
        """Select variant and execution strategy for a model workload."""
        policy = self.controller.current_policy()

        # Filter to matching model
        candidates = [v for v in self.variants if v.model_id == model_id]
        if not candidates:
            return ExecutionPlan(
                ExecutionDecision.REJECT,
                None,
                Precision.INT4,
                0,
                0,
                0,
                f"No variants registered for {model_id}",
            )

        # Filter by hardware capability
        feasible = self._filter_feasible(candidates, policy)
        if not feasible:
            # Tactical context: if local execution cannot satisfy constraints,
            # defer to a peer node only when policy allows external inference.
            if policy.allow_external_inference:
                return ExecutionPlan(
                    ExecutionDecision.DEFER_TO_PEER,
                    None,
                    Precision.INT4,
                    requested_tokens,
                    0,
                    1,
                    f"No feasible local variant for {model_id}; deferring to peer.",
                )
            return ExecutionPlan(
                ExecutionDecision.SUMMARIZE_INSTEAD,
                None,
                Precision.INT4,
                min(requested_tokens, 128),
                0,
                1,
                "No feasible variant and no peer; falling back to summarization.",
            )

        # Rank: prefer smallest memory footprint that still fits
        feasible.sort(key=lambda v: v.size_mb)
        chosen = feasible[0]

        # Constrain tokens/context based on mode
        max_tokens = min(requested_tokens, self._token_ceiling(policy, chosen))
        max_context = chosen.max_context
        if policy.mode in (
            OperatingMode.MODE_B_CPU_CONSTRAINED,
            OperatingMode.MODE_D_OFFLINE_SURVIVAL,
        ):
            max_context = min(max_context, 2048)

        return ExecutionPlan(
            decision=ExecutionDecision.RUN_LOCAL,
            variant=chosen,
            precision=chosen.precision,
            max_tokens=max_tokens,
            max_context=max_context,
            max_batch=1 if policy.mode != OperatingMode.MODE_A_FULL_EDGE else 4,
            reason=(
                f"Selected {chosen.variant_tag} ({chosen.size_mb:.0f} MB) "
                f"for {self.profile.tier.value}"
            ),
        )

    def _filter_feasible(
        self, candidates: List[ModelVariant], policy: ModePolicy
    ) -> List[ModelVariant]:
        feasible = []
        for variant in candidates:
            if variant.requires_gpu and not policy.allow_gpu:
                continue
            if variant.requires_gpu and not self.profile.gpu_detected:
                continue
            if variant.min_ram_gb > self.profile.ram_available_gb:
                continue
            feasible.append(variant)
        return feasible

    @staticmethod
    def _token_ceiling(policy: ModePolicy, variant: ModelVariant) -> int:
        if policy.mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL:
            return 256
        if policy.mode == OperatingMode.MODE_B_CPU_CONSTRAINED:
            return 512
        return variant.max_context  # modes A/C: full capacity
