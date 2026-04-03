"""CPU-first model execution planner for austere edge nodes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Dict, List

from src.edge_runtime.degradation_controller import DegradationController, OperatingMode
from src.edge_runtime.hardware_profiler import NodeProfile

logger = logging.getLogger("s3m.edge_runtime.model_planner")


class QuantizationLevel(str, Enum):
    Q4 = "Q4"
    Q8 = "Q8"
    FP16 = "FP16"


class ExecutionAction(str, Enum):
    RUN_LOCAL = "RUN_LOCAL"
    DEFER_TO_PEER = "DEFER_TO_PEER"
    SUMMARIZE_INSTEAD = "SUMMARIZE_INSTEAD"
    REJECT = "REJECT"


@dataclass(slots=True, frozen=True)
class ModelVariant:
    model_name: str
    quantization: QuantizationLevel
    min_memory_mb: int
    requires_gpu: bool
    preferred_latency_ms: int


@dataclass(slots=True, frozen=True)
class ExecutionPlan:
    action: ExecutionAction
    selected_variant: ModelVariant | None
    rationale: str
    constraints: Dict[str, int | bool | str]


class ModelExecutionPlanner:
    """Computes execution decisions using tier and current degradation policy."""

    def __init__(self, profile: NodeProfile, controller: DegradationController) -> None:
        self.profile = profile
        self.controller = controller
        self.catalog = self._build_catalog()

    def plan(self, task_name: str, priority: int = 1) -> ExecutionPlan:
        """
        Return execution decision for an inference task.

        Priority: 0 critical, 1 normal, 2 background.
        """
        mode = self.controller.current_mode
        policy = self.controller.policy()
        variants = self.catalog.get(task_name, [])

        if not variants:
            return ExecutionPlan(
                action=ExecutionAction.REJECT,
                selected_variant=None,
                rationale=f"Unknown task model: {task_name}",
                constraints={"mode": mode.value, "priority": priority},
            )

        affordable = [
            v
            for v in variants
            if v.min_memory_mb <= self.profile.total_memory_mb
            and (policy.allow_gpu or not v.requires_gpu)
        ]

        if affordable:
            selected = self._pick_best(affordable)
            if mode == OperatingMode.OFFLINE_SURVIVAL and priority >= 2:
                # Preserve compute budget for tactical-critical operations under no-link state.
                return ExecutionPlan(
                    action=ExecutionAction.SUMMARIZE_INSTEAD,
                    selected_variant=None,
                    rationale="Background task converted to summary in offline survival mode",
                    constraints=self._constraint_map(priority),
                )
            return ExecutionPlan(
                action=ExecutionAction.RUN_LOCAL,
                selected_variant=selected,
                rationale=f"Selected {selected.quantization.value} variant for local execution",
                constraints=self._constraint_map(priority),
            )

        if mode in {OperatingMode.INTERMITTENT_LINK, OperatingMode.FULL_EDGE}:
            return ExecutionPlan(
                action=ExecutionAction.DEFER_TO_PEER,
                selected_variant=None,
                rationale="No local variant fits current memory or policy constraints",
                constraints=self._constraint_map(priority),
            )

        if priority == 0:
            return ExecutionPlan(
                action=ExecutionAction.SUMMARIZE_INSTEAD,
                selected_variant=None,
                rationale="Critical request summarized due to severe local constraints",
                constraints=self._constraint_map(priority),
            )

        return ExecutionPlan(
            action=ExecutionAction.REJECT,
            selected_variant=None,
            rationale="Cannot satisfy request in current austere mode",
            constraints=self._constraint_map(priority),
        )

    def _constraint_map(self, priority: int) -> Dict[str, int | bool | str]:
        policy = self.controller.policy()
        return {
            "mode": self.controller.current_mode.value,
            "priority": priority,
            "allow_gpu": policy.allow_gpu,
            "max_concurrent_models": policy.max_concurrent_models,
            "memory_mb": self.profile.total_memory_mb,
        }

    def _pick_best(self, variants: List[ModelVariant]) -> ModelVariant:
        # CPU-first policy: prefer non-GPU variants and smallest quantization footprint.
        ranked = sorted(
            variants,
            key=lambda v: (
                v.requires_gpu,
                v.min_memory_mb,
                0
                if v.quantization == QuantizationLevel.Q4
                else 1
                if v.quantization == QuantizationLevel.Q8
                else 2,
                v.preferred_latency_ms,
            ),
        )
        return ranked[0]

    def _build_catalog(self) -> Dict[str, List[ModelVariant]]:
        # Quad-engine variants tuned for tactical disconnected execution.
        engines = ["phi3", "grok", "mistral", "allam"]
        catalog: Dict[str, List[ModelVariant]] = {}
        for engine in engines:
            catalog[engine] = [
                ModelVariant(
                    model_name=engine,
                    quantization=QuantizationLevel.Q4,
                    min_memory_mb=4096,
                    requires_gpu=False,
                    preferred_latency_ms=1200,
                ),
                ModelVariant(
                    model_name=engine,
                    quantization=QuantizationLevel.Q8,
                    min_memory_mb=8192,
                    requires_gpu=False,
                    preferred_latency_ms=850,
                ),
                ModelVariant(
                    model_name=engine,
                    quantization=QuantizationLevel.FP16,
                    min_memory_mb=12288,
                    requires_gpu=True,
                    preferred_latency_ms=420,
                ),
            ]
        logger.info("Model catalog initialized entries=%s", len(catalog))
        return catalog
