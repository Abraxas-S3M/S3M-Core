"""
S3M CPU Training Precision Policy.
Selects optimal numerical precision based on detected hardware capabilities.
Research basis: BF16 mixed precision provides 86%+ throughput gain on AVX-512 BF16.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging

from src.edge_runtime.hardware_profiler import NodeProfile


logger = logging.getLogger("s3m.training.precision")


class TrainingPrecision(str, Enum):
    FP32 = "fp32"
    BF16_MIXED = "bf16_mixed"  # BF16 forward/backward, FP32 master weights
    FP16_MIXED = "fp16_mixed"  # FP16 forward/backward, FP32 master weights
    INT8_MIXED = "int8_mixed"  # INT8 forward, FP32 backward
    QAT_INT4 = "qat_int4"  # 4-bit quantized forward, FP32 master weights


@dataclass(frozen=True)
class PrecisionConfig:
    """Immutable precision configuration for a training job."""

    training_precision: TrainingPrecision
    master_weight_dtype: str  # "float32" always
    forward_dtype: str  # "bfloat16", "float16", "float32", "int4"
    gradient_dtype: str  # usually matches forward_dtype or "float32"
    use_gradient_checkpointing: bool  # True on constrained nodes
    use_gradient_clipping: bool  # True always for QAT
    gradient_clip_norm: float  # 0.5 for QAT, 1.0 for standard
    use_tanh_soft_clipping: bool  # True for QAT_INT4 paths
    tanh_clipping_scale: float  # 3.0 per research
    numa_aware_threading: bool
    optimal_num_threads: int
    torch_compile_backend: str  # "inductor" or "ipex"
    reason: str  # human-readable explanation


class PrecisionPolicyEngine:
    """
    Selects optimal training precision based on hardware profile.

    Decision tree (from research):
    1. If avx512_bf16 -> BF16_MIXED (86%+ throughput gain, safest for convergence)
    2. If avx512 without bf16 -> FP32 with torch.compile (still benefits from wider SIMD)
    3. If avx2 only -> FP32 with channels-last optimization where applicable
    4. If ARM with NEON -> FP32 (ARM BF16 support varies)
    5. For QAT paths -> QAT_INT4 with tanh clipping regardless of ISA
    """

    _VALID_TASK_TYPES = {
        "adapter_tuning",
        "classifier_retrain",
        "distillation",
        "qat_4bit",
        "full_finetune",
    }

    def __init__(self, profile: NodeProfile):
        self.profile = profile

    def select_precision(self, task_type: str = "adapter_tuning") -> PrecisionConfig:
        """Select optimal precision for the given task type."""
        if not isinstance(task_type, str):
            logger.warning("Non-string task_type received; defaulting to adapter_tuning.")
            task_key = "adapter_tuning"
        else:
            task_key = task_type.strip().lower()

        if task_key not in self._VALID_TASK_TYPES:
            logger.warning("Unknown task_type '%s'; defaulting to adapter_tuning.", task_type)
            task_key = "adapter_tuning"

        if task_key == "qat_4bit":
            return self._select_for_qat()

        selected = self._select_for_adapter_tuning()
        if task_key == "full_finetune":
            reason = f"{selected.reason} Full finetune path keeps master weights in FP32."
            return PrecisionConfig(**{**selected.__dict__, "reason": reason})
        if task_key == "distillation":
            reason = f"{selected.reason} Distillation remains CPU-safe for disconnected operations."
            return PrecisionConfig(**{**selected.__dict__, "reason": reason})
        if task_key == "classifier_retrain":
            reason = f"{selected.reason} Classifier retraining favors deterministic FP math."
            return PrecisionConfig(**{**selected.__dict__, "reason": reason})
        return selected

    def _select_for_adapter_tuning(self) -> PrecisionConfig:
        """Standard adapter tuning — prefer BF16 if available."""
        checkpointing = self.profile.ram_available_gb < 16.0
        numa_nodes = max(1, int(self.profile.numa_node_count))
        thread_count = self._compute_optimal_threads()
        backend = "ipex" if self.profile.avx512_supported or self.profile.avx2_supported else "inductor"

        if self.profile.avx512_bf16_supported:
            reason = (
                "AVX-512 BF16 detected; selecting BF16 mixed precision for CPU throughput while preserving "
                "FP32 master-weight stability."
            )
            return PrecisionConfig(
                training_precision=TrainingPrecision.BF16_MIXED,
                master_weight_dtype="float32",
                forward_dtype="bfloat16",
                gradient_dtype="bfloat16",
                use_gradient_checkpointing=checkpointing,
                use_gradient_clipping=False,
                gradient_clip_norm=1.0,
                use_tanh_soft_clipping=False,
                tanh_clipping_scale=0.0,
                numa_aware_threading=numa_nodes > 1,
                optimal_num_threads=thread_count,
                torch_compile_backend=backend,
                reason=reason,
            )

        if self.profile.avx512_supported:
            reason = "AVX-512 detected without BF16; retaining FP32 for convergence safety and wide-SIMD execution."
        elif self.profile.avx2_supported:
            reason = "AVX2 detected; selecting FP32 with CPU vectorization-friendly execution."
        elif self.profile.arm_sve_supported:
            reason = "ARM SVE detected; selecting conservative FP32 due to variable BF16 support across targets."
        elif self.profile.arm_neon_supported:
            reason = "ARM NEON detected; selecting FP32 for deterministic field retraining behavior."
        else:
            reason = "No advanced CPU ISA extension detected; selecting baseline FP32."

        return PrecisionConfig(
            training_precision=TrainingPrecision.FP32,
            master_weight_dtype="float32",
            forward_dtype="float32",
            gradient_dtype="float32",
            use_gradient_checkpointing=checkpointing,
            use_gradient_clipping=False,
            gradient_clip_norm=1.0,
            use_tanh_soft_clipping=False,
            tanh_clipping_scale=0.0,
            numa_aware_threading=numa_nodes > 1,
            optimal_num_threads=thread_count,
            torch_compile_backend=backend,
            reason=reason,
        )

    def _select_for_qat(self) -> PrecisionConfig:
        """4-bit QAT — always uses tanh soft clipping, INT4 forward."""
        numa_nodes = max(1, int(self.profile.numa_node_count))
        return PrecisionConfig(
            training_precision=TrainingPrecision.QAT_INT4,
            master_weight_dtype="float32",
            forward_dtype="int4",
            gradient_dtype="float32",
            use_gradient_checkpointing=self.profile.ram_available_gb < 16.0,
            use_gradient_clipping=True,
            gradient_clip_norm=0.5,
            use_tanh_soft_clipping=True,
            tanh_clipping_scale=3.0,
            numa_aware_threading=numa_nodes > 1,
            optimal_num_threads=self._compute_optimal_threads(),
            torch_compile_backend="inductor",
            reason="QAT INT4 task selected; enabling tanh soft clipping to stabilize low-bit tactical adaptation.",
        )

    def _compute_optimal_threads(self) -> int:
        """
        Reserve one CPU thread for data staging and telemetry tasks.

        Tactical context:
        This keeps ingestion responsive during contested communications while
        on-node training occupies the remaining compute budget.
        """
        total_cores = max(1, int(self.profile.cpu_cores))
        numa_nodes = max(1, int(self.profile.numa_node_count))
        if numa_nodes > 1:
            cores_per_node = max(1, total_cores // numa_nodes)
            return max(1, cores_per_node - 1)
        return max(1, total_cores - 1)

    def get_torch_autocast_config(self) -> dict:
        """Return kwargs for torch.amp.autocast('cpu', ...) based on policy."""
        config = self.select_precision()
        if config.training_precision is TrainingPrecision.BF16_MIXED:
            return {"enabled": True, "dtype": "bfloat16"}
        if config.training_precision is TrainingPrecision.FP16_MIXED:
            return {"enabled": True, "dtype": "float16"}
        return {"enabled": False, "dtype": "float32"}

    def get_environment_recommendations(self) -> dict:
        """Return recommended environment variables for CPU training."""
        numa_nodes = max(1, int(self.profile.numa_node_count))
        threads = str(self._compute_optimal_threads())
        recommendations = {
            "OMP_NUM_THREADS": threads,
            "KMP_AFFINITY": "granularity=fine,compact,1,0",
            "KMP_BLOCKTIME": "1",
            "MALLOC_CONF": "",
            "LD_PRELOAD": "",
        }
        if numa_nodes > 1:
            recommendations["KMP_AFFINITY"] = "granularity=fine,compact,1,0"
            recommendations["MALLOC_CONF"] = (
                "background_thread:true,metadata_thp:auto,dirty_decay_ms:5000,muzzy_decay_ms:5000"
            )
            recommendations["LD_PRELOAD"] = "/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4"
        return recommendations

