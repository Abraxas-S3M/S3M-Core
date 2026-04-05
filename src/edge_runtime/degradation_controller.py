"""
Mode degradation controller for denied-edge mission continuity.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Callable, Dict, List, Optional

from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile
try:
    from src.edge_runtime.offline_brain import OfflineBrain
except Exception:  # pragma: no cover - optional while module staging is incomplete
    OfflineBrain = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class OperatingMode(str, Enum):
    MODE_A_FULL_EDGE = "full_edge"
    MODE_B_CPU_CONSTRAINED = "cpu_constrained"
    MODE_C_INTERMITTENT_LINK = "intermittent_link"
    MODE_D_OFFLINE_SURVIVAL = "offline_survival"


@dataclass(frozen=True)
class ModePolicy:
    mode: OperatingMode
    max_concurrent_models: int
    allow_gpu: bool
    allow_continuous_summarization: bool
    allow_large_transfers: bool
    allow_external_inference: bool
    summarization_interval_sec: int
    max_frame_rate: int
    queue_outbound: bool
    description: str


MODE_POLICIES: Dict[OperatingMode, ModePolicy] = {
    OperatingMode.MODE_A_FULL_EDGE: ModePolicy(
        mode=OperatingMode.MODE_A_FULL_EDGE,
        max_concurrent_models=4,
        allow_gpu=True,
        allow_continuous_summarization=True,
        allow_large_transfers=True,
        allow_external_inference=True,
        summarization_interval_sec=0,
        max_frame_rate=30,
        queue_outbound=False,
        description="Full capability posture with stable links and compute headroom.",
    ),
    OperatingMode.MODE_B_CPU_CONSTRAINED: ModePolicy(
        mode=OperatingMode.MODE_B_CPU_CONSTRAINED,
        max_concurrent_models=2,
        allow_gpu=False,
        allow_continuous_summarization=False,
        allow_large_transfers=True,
        allow_external_inference=True,
        summarization_interval_sec=60,
        max_frame_rate=10,
        queue_outbound=False,
        description="CPU-constrained posture preserving tactical responsiveness.",
    ),
    OperatingMode.MODE_C_INTERMITTENT_LINK: ModePolicy(
        mode=OperatingMode.MODE_C_INTERMITTENT_LINK,
        max_concurrent_models=2,
        allow_gpu=True,
        allow_continuous_summarization=False,
        allow_large_transfers=False,
        allow_external_inference=False,
        summarization_interval_sec=120,
        max_frame_rate=15,
        queue_outbound=True,
        description="Intermittent-link posture prioritizing store-and-forward traffic.",
    ),
    OperatingMode.MODE_D_OFFLINE_SURVIVAL: ModePolicy(
        mode=OperatingMode.MODE_D_OFFLINE_SURVIVAL,
        max_concurrent_models=1,
        allow_gpu=False,
        allow_continuous_summarization=False,
        allow_large_transfers=False,
        allow_external_inference=False,
        summarization_interval_sec=300,
        max_frame_rate=5,
        queue_outbound=True,
        description="Offline survival posture maximizing endurance and mission continuity.",
    ),
}


@dataclass
class ModeTransition:
    from_mode: OperatingMode
    to_mode: OperatingMode
    reason: str
    timestamp: str


class PrecisionPolicyEngine:
    """Recommend training precision for sustained edge mission operations."""

    @staticmethod
    def recommend_training_precision(profile: NodeProfile, training_spec: Dict[str, object]) -> str:
        requires_bf16 = bool(training_spec.get("requires_bf16", False))
        cpu_arch = str(profile.cpu_arch or "").lower()
        bf16_capable_arch = cpu_arch in {"aarch64", "arm64", "x86_64", "amd64"}
        has_bf16_headroom = float(profile.ram_available_gb) >= 8.0

        if requires_bf16 and bf16_capable_arch and has_bf16_headroom:
            return "bf16_mixed"
        if requires_bf16:
            return "fp32"
        if bf16_capable_arch and has_bf16_headroom:
            return "bf16_mixed"
        return "int8_qat"


class DegradationController:
    """State machine converting link/thermal/resource signals into runtime modes."""

    def __init__(self, profile: NodeProfile) -> None:
        self.profile = profile
        self.current_mode: OperatingMode = self._initial_mode(profile)
        self._transitions: List[ModeTransition] = []
        self._subscribers: List[Callable[[OperatingMode, ModePolicy], None]] = []
        self._link_healthy: bool = bool(profile.active_links)
        self._link_last_seen: float = time.time() if self._link_healthy else 0.0
        self.offline_brain: Optional[OfflineBrain] = None
        if self.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL:
            self._ensure_offline_brain("initial_offline_survival")

    def current_policy(self) -> ModePolicy:
        return MODE_POLICIES[self.current_mode]

    def subscribe(self, callback: Callable[[OperatingMode, ModePolicy], None]) -> None:
        self._subscribers.append(callback)

    def report_link_state(self, any_bearer_up: bool) -> None:
        self._link_healthy = bool(any_bearer_up)
        if self._link_healthy:
            self._link_last_seen = time.time()
        self._reevaluate()

    def report_thermal(self, temp_c: float) -> None:
        self.profile.thermal_zone_c = float(temp_c)
        self._reevaluate()

    def force_mode(self, mode: OperatingMode, reason: str) -> None:
        self._transition(mode, reason)

    def get_transition_log(self) -> List[Dict[str, str]]:
        return [
            {
                "from_mode": t.from_mode.value,
                "to_mode": t.to_mode.value,
                "reason": t.reason,
                "timestamp": t.timestamp,
            }
            for t in self._transitions
        ]

    def _reevaluate(self) -> None:
        no_link_for = 0.0 if self._link_healthy else max(0.0, time.time() - self._link_last_seen)
        thermal = self.profile.thermal_zone_c

        if (not self.profile.gpu_detected and no_link_for > 300.0) or no_link_for > 600.0:
            self._transition(OperatingMode.MODE_D_OFFLINE_SURVIVAL, f"link_down_{int(no_link_for)}s")
            return

        if no_link_for > 60.0:
            self._transition(OperatingMode.MODE_C_INTERMITTENT_LINK, f"link_unstable_{int(no_link_for)}s")
            return

        if (not self.profile.gpu_detected) or (thermal is not None and thermal > 85.0) or (self.profile.ram_available_gb < 4.0):
            self._transition(OperatingMode.MODE_B_CPU_CONSTRAINED, "resource_constrained")
            return

        self._transition(OperatingMode.MODE_A_FULL_EDGE, "nominal")

    def _transition(self, new_mode: OperatingMode, reason: str) -> None:
        if new_mode == self.current_mode:
            return
        transition = ModeTransition(
            from_mode=self.current_mode,
            to_mode=new_mode,
            reason=str(reason),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.current_mode = new_mode
        self._transitions.append(transition)
        if new_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL:
            self._ensure_offline_brain(reason)
        policy = MODE_POLICIES[new_mode]
        for callback in list(self._subscribers):
            try:
                callback(new_mode, policy)
            except Exception:
                continue

    def _ensure_offline_brain(self, reason: str) -> None:
        if OfflineBrain is None:
            return
        if self.offline_brain is None:
            self.offline_brain = OfflineBrain()
        try:
            self.offline_brain.activate(reason=str(reason))
        except Exception:
            return

    @staticmethod
    def _initial_mode(profile: NodeProfile) -> OperatingMode:
        if profile.tier == HardwareTier.CPU_AUSTERE:
            return OperatingMode.MODE_B_CPU_CONSTRAINED
        if not profile.active_links:
            return OperatingMode.MODE_D_OFFLINE_SURVIVAL
        return OperatingMode.MODE_A_FULL_EDGE

    @staticmethod
    def service_tiers() -> Dict[str, Dict[str, object]]:
        full_model_finetune_large = {
            "tier": 2,
            "cpu_safe": False,
            "offline_safe": True,
            "low_bw_safe": False,
            "max_memory_mb": 32768,
            "description": "Full parameter fine-tune requiring GPU and significant RAM",
        }
        return {
            "llm_inference_q4": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "threat_classifier": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "anomaly_detector": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "behavior_tree_exec": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "sensor_fusion_ekf": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "arabic_nlp_keyword": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "object_detector": {"tier": 1, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "llm_inference_fp16": {"tier": 1, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "bulk_log_sync": {"tier": 1, "cpu_safe": True, "offline_safe": False, "low_bw_safe": True},
            "adapter_finetune_small": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": True,
                "low_bw_safe": True,
                "max_memory_mb": 4096,
                "description": "LoRA adapter tuning on <10k samples, CPU-safe",
            },
            "classifier_retrain": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": True,
                "low_bw_safe": True,
                "max_memory_mb": 1024,
                "description": "Retrain sklearn/small-torch classifiers on edge",
            },
            "knowledge_distillation": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": True,
                "low_bw_safe": True,
                "max_memory_mb": 6144,
                "description": "Teacher-student distillation using quantized models on CPU",
            },
            "federated_adapter_merge": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": False,
                "low_bw_safe": True,
                "max_memory_mb": 2048,
                "description": "Merge LoRA adapter deltas from peer nodes",
            },
            "classifier_retrain_small": {
                "tier": 0,
                "cpu_safe": True,
                "offline_safe": True,
                "low_bw_safe": True,
                "max_memory_mb": 1024,
                "min_cores": 2,
                "description": "Retrain sklearn/small-torch classifiers on edge data",
            },
            "adapter_finetune_small_llm": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": True,
                "low_bw_safe": True,
                "max_memory_mb": 4096,
                "min_cores": 4,
                "min_ram_gb": 8.0,
                "requires_bf16": False,  # works without, faster with
                "description": "LoRA adapter tuning with tanh-clipped 4-bit QAT on CPU",
            },
            "distillation_job_medium": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": True,
                "low_bw_safe": True,
                "max_memory_mb": 6144,
                "min_cores": 8,
                "min_ram_gb": 16.0,
                "requires_bf16": True,  # recommended for throughput
                "description": "Teacher-student distillation using quantized CPU models",
            },
            "federated_adapter_aggregation": {
                "tier": 1,
                "cpu_safe": True,
                "offline_safe": False,
                "low_bw_safe": True,
                "max_memory_mb": 2048,
                "min_cores": 2,
                "description": "Merge LoRA adapter deltas from peer nodes",
            },
            "full_weight_finetune_large": {
                "tier": 2,
                "cpu_safe": False,
                "offline_safe": True,
                "low_bw_safe": False,
                "max_memory_mb": 32768,
                "description": "Full parameter fine-tune requiring GPU",
            },
            # Backward compatibility alias
            "model_fine_tune": {
                "tier": 2,
                "cpu_safe": False,
                "offline_safe": True,
                "low_bw_safe": False,
                "_deprecated": True,
                "_alias_for": "full_weight_finetune_large",
                "description": "DEPRECATED: use specific training tier instead",
            },
            "simulation_engine": {"tier": 2, "cpu_safe": False, "offline_safe": True, "low_bw_safe": False},
            "full_model_finetune_large": full_model_finetune_large,
        }

    def can_execute_training(self, training_tier: str, profile: NodeProfile = None) -> dict:
        """
        Check if a specific training operation can run on current hardware and mode.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "recommended_precision": str,
                "estimated_memory_mb": int,
                "warnings": list[str]
            }
        """
        active_profile = profile or self.profile
        tiers = self.service_tiers()
        if training_tier not in tiers:
            return {
                "allowed": False,
                "reason": f"Unknown training tier '{training_tier}'.",
                "recommended_precision": "int8_qat",
                "estimated_memory_mb": 0,
                "warnings": [],
            }

        warnings: List[str] = []
        tier_spec = dict(tiers[training_tier])
        if bool(tier_spec.get("_deprecated", False)):
            alias_for = str(tier_spec.get("_alias_for", "")).strip()
            logger.warning(
                "Deprecated training tier '%s' requested; redirecting to '%s'.",
                training_tier,
                alias_for or "unknown",
            )
            warnings.append(
                f"Training tier '{training_tier}' is deprecated; use '{alias_for or 'unknown'}' for mission planning."
            )
            if alias_for and alias_for in tiers:
                tier_spec = dict(tiers[alias_for])

        estimated_memory_mb = int(tier_spec.get("max_memory_mb", 0) or 0)
        recommended_precision = PrecisionPolicyEngine.recommend_training_precision(active_profile, tier_spec)

        cpu_mode = (not self.current_policy().allow_gpu) or (not bool(active_profile.gpu_detected))
        if cpu_mode and not bool(tier_spec.get("cpu_safe", True)):
            return {
                "allowed": False,
                "reason": f"Training tier '{training_tier}' is not CPU-safe in current mode.",
                "recommended_precision": recommended_precision,
                "estimated_memory_mb": estimated_memory_mb,
                "warnings": warnings,
            }

        required_ram_gb = float(tier_spec.get("min_ram_gb", 0.0) or 0.0)
        if estimated_memory_mb > 0:
            required_ram_gb = max(required_ram_gb, estimated_memory_mb / 1024.0)
        available_ram_gb = float(active_profile.ram_available_gb)
        if required_ram_gb > 0 and available_ram_gb < required_ram_gb:
            return {
                "allowed": False,
                "reason": (
                    f"Insufficient RAM for tier '{training_tier}' "
                    f"(required {required_ram_gb:.1f} GB, available {available_ram_gb:.1f} GB)."
                ),
                "recommended_precision": recommended_precision,
                "estimated_memory_mb": estimated_memory_mb,
                "warnings": warnings,
            }

        min_cores = int(tier_spec.get("min_cores", 1) or 1)
        if int(active_profile.cpu_cores) < min_cores:
            return {
                "allowed": False,
                "reason": (
                    f"Insufficient CPU cores for tier '{training_tier}' "
                    f"(required {min_cores}, available {active_profile.cpu_cores})."
                ),
                "recommended_precision": recommended_precision,
                "estimated_memory_mb": estimated_memory_mb,
                "warnings": warnings,
            }

        offline_now = self.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL or not bool(active_profile.active_links)
        if offline_now and not bool(tier_spec.get("offline_safe", True)):
            return {
                "allowed": False,
                "reason": f"Training tier '{training_tier}' is not allowed in offline posture.",
                "recommended_precision": recommended_precision,
                "estimated_memory_mb": estimated_memory_mb,
                "warnings": warnings,
            }

        if bool(tier_spec.get("requires_bf16", False)) and recommended_precision != "bf16_mixed":
            warnings.append("bf16 is recommended for this tier; expect reduced throughput on current node.")

        return {
            "allowed": True,
            "reason": f"Training tier '{training_tier}' is executable under current mode and resources.",
            "recommended_precision": recommended_precision,
            "estimated_memory_mb": estimated_memory_mb,
            "warnings": warnings,
        }
