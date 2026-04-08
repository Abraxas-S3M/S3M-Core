"""
S3M Quad-Engine Registry
Four sovereign LLM engines running as one unified system.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from enum import Enum


class EngineID(Enum):
    PHI3_MEDIUM = "phi3-medium"
    GROK1 = "grok1-314b"
    MIXTRAL = "mixtral-8x7b"
    ALLAM = "allam-7b"


class TaskDomain(Enum):
    TACTICAL = "tactical"
    REASONING = "reasoning"
    PLANNING = "planning"
    ARABIC_NLP = "arabic_nlp"
    CONSENSUS = "consensus"


@dataclass
class EngineConfig:
    engine_id: EngineID
    name: str
    provider: str
    params: str
    model_filename: str
    quantization: str
    runtime: str
    hf_repo: str
    gcs_path: str
    local_path: str
    max_tokens: int
    context_window: int
    primary_domain: TaskDomain
    loaded: bool = False
    latency_tier: str = "medium"
    inference_latency_ms: float = 0.0
    throughput_tok_s: float = 0.0
    memory_footprint_gb: float = 0.0
    is_moe: bool = False
    moe_experts: int = 0
    active_experts: int = 0
    fp16_size_gb: float = 0.0
    q4_size_gb: float = 0.0
    training_tier: str = "gpu_required"  # gpu_required | cpu_capable | multi_gpu
    warm_state: bool = False
    confidence_prior: float = 0.75
    capabilities: Optional[Dict[Union[TaskDomain, str], float]] = field(default=None)
    version_tag: Optional[str] = "v1.0.0"
    sha256_hash: Optional[str] = None
    # Training capability fields (new)
    adapter_tuning_allowed: bool = True
    adapter_tuning_min_ram_gb: float = 6.0
    adapter_tuning_bf16_benefit: bool = True
    preferred_student_model: Optional[str] = None
    gguf_export_supported: bool = True
    onnx_export_supported: bool = False
    openvino_export_supported: bool = False
    cpu_training_precision_default: str = "bf16_mixed"
    max_lora_rank: int = 16
    cpu_inference_tok_s_target: float = 0.0
    cpu_inference_ram_mb: int = 0

    def __post_init__(self):
        """Initialize mission-routing capability priors for tactical orchestration."""
        if self.capabilities is None:
            self.capabilities = self._default_capabilities()

    def _default_capabilities(self) -> Dict[TaskDomain, float]:
        """Provide baseline confidence by domain for field routing decisions."""
        base = {
            TaskDomain.TACTICAL: 0.5,
            TaskDomain.REASONING: 0.5,
            TaskDomain.PLANNING: 0.5,
            TaskDomain.ARABIC_NLP: 0.5,
        }
        base[self.primary_domain] = 0.9
        return base

    def get_capability_score(self, domain: TaskDomain) -> float:
        """Get capability score for a domain with enum/string key tolerance."""
        if self.capabilities is None:
            return 0.5
        if domain in self.capabilities:
            return float(self.capabilities[domain])
        if domain.value in self.capabilities:
            return float(self.capabilities[domain.value])
        return 0.5


ENGINE_CONFIGS: Dict[EngineID, EngineConfig] = {
    EngineID.PHI3_MEDIUM: EngineConfig(
        engine_id=EngineID.PHI3_MEDIUM,
        name="Phi-3 Medium",
        provider="Microsoft",
        params="14B",
        model_filename="phi-3-medium-4k-instruct.Q4_K_M.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="microsoft/Phi-3-medium-4k-instruct",
        gcs_path="gs://s3m-weight-vault/phi3-medium/phi-3-medium-4k-instruct.Q4_K_M.gguf",
        local_path="models/phi3-medium/phi-3-medium-4k-instruct.Q4_K_M.gguf",
        max_tokens=1024,
        context_window=4096,
        primary_domain=TaskDomain.TACTICAL,
        latency_tier="fast",
        inference_latency_ms=45.0,
        throughput_tok_s=22.0,
        memory_footprint_gb=10.0,
        is_moe=False,
        fp16_size_gb=28.0,
        q4_size_gb=8.5,
        confidence_prior=0.88,
        training_tier="gpu_required",
        capabilities={
            TaskDomain.TACTICAL: 0.95,
            TaskDomain.REASONING: 0.80,
            TaskDomain.PLANNING: 0.78,
            TaskDomain.ARABIC_NLP: 0.45,
        },
    ),
    EngineID.GROK1: EngineConfig(
        engine_id=EngineID.GROK1,
        name="Grok-1",
        provider="xAI",
        params="314B (MoE)",
        model_filename="grok-1.Q4_K_M.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="xai-org/grok-1",
        gcs_path="gs://s3m-weight-vault/grok1/grok-1.Q4_K_M.gguf",
        local_path="models/grok1/grok-1.Q4_K_M.gguf",
        max_tokens=2048,
        context_window=8192,
        primary_domain=TaskDomain.REASONING,
        latency_tier="slow",
        inference_latency_ms=180.0,
        throughput_tok_s=8.0,
        memory_footprint_gb=85.0,
        is_moe=True,
        moe_experts=8,
        active_experts=2,
        fp16_size_gb=300.0,
        q4_size_gb=80.0,
        confidence_prior=0.92,
        training_tier="multi_gpu",
        capabilities={
            TaskDomain.TACTICAL: 0.70,
            TaskDomain.REASONING: 0.97,
            TaskDomain.PLANNING: 0.85,
            TaskDomain.ARABIC_NLP: 0.50,
        },
    ),
    EngineID.MIXTRAL: EngineConfig(
        engine_id=EngineID.MIXTRAL,
        name="Mixtral 8x7B",
        provider="Mistral AI",
        params="46.7B (MoE)",
        model_filename="mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="mistralai/Mixtral-8x7B-Instruct-v0.1",
        gcs_path="gs://s3m-weight-vault/mixtral/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
        local_path="models/mixtral/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
        max_tokens=2048,
        context_window=32768,
        primary_domain=TaskDomain.PLANNING,
        latency_tier="medium",
        inference_latency_ms=75.0,
        throughput_tok_s=18.0,
        memory_footprint_gb=28.0,
        is_moe=True,
        moe_experts=8,
        active_experts=2,
        fp16_size_gb=93.0,
        q4_size_gb=26.0,
        confidence_prior=0.87,
        training_tier="gpu_required",
        capabilities={
            TaskDomain.TACTICAL: 0.65,
            TaskDomain.REASONING: 0.78,
            TaskDomain.PLANNING: 0.95,
            TaskDomain.ARABIC_NLP: 0.55,
        },
    ),
    EngineID.ALLAM: EngineConfig(
        engine_id=EngineID.ALLAM,
        name="ALLaM-7B",
        provider="SDAIA",
        params="7B",
        model_filename="allam-7b-instruct.Q4_K_M.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="humain-ai/ALLaM-7B-Instruct-preview",
        gcs_path="gs://s3m-weight-vault/allam/allam-7b-instruct.Q4_K_M.gguf",
        local_path="models/allam/allam-7b-instruct.Q4_K_M.gguf",
        max_tokens=1024,
        context_window=4096,
        primary_domain=TaskDomain.ARABIC_NLP,
        latency_tier="fast",
        inference_latency_ms=35.0,
        throughput_tok_s=28.0,
        memory_footprint_gb=5.5,
        is_moe=False,
        fp16_size_gb=14.0,
        q4_size_gb=4.0,
        confidence_prior=0.83,
        training_tier="gpu_required",
        capabilities={
            TaskDomain.TACTICAL: 0.58,
            TaskDomain.REASONING: 0.62,
            TaskDomain.PLANNING: 0.60,
            TaskDomain.ARABIC_NLP: 0.95,
        },
    ),
}


DOMAIN_ROUTING = {
    TaskDomain.TACTICAL: EngineID.PHI3_MEDIUM,
    TaskDomain.REASONING: EngineID.GROK1,
    TaskDomain.PLANNING: EngineID.MIXTRAL,
    TaskDomain.ARABIC_NLP: EngineID.ALLAM,
}


class EngineRegistry:
    def __init__(self):
        self.configs = ENGINE_CONFIGS
        self.active_engines: Dict[EngineID, bool] = {e: False for e in EngineID}

    def get_config(self, engine_id: EngineID) -> EngineConfig:
        return self.configs[engine_id]

    def get_engine_for_domain(self, domain: TaskDomain) -> EngineConfig:
        engine_id = DOMAIN_ROUTING[domain]
        return self.configs[engine_id]

    def get_all_engines(self) -> List[EngineConfig]:
        return list(self.configs.values())

    def mark_loaded(self, engine_id: EngineID):
        self.active_engines[engine_id] = True

    def get_status(self) -> Dict[str, bool]:
        return {e.value: self.active_engines[e] for e in EngineID}

    def get_engines_by_tier(self, tier: str) -> List[EngineConfig]:
        """Return engines matching a latency tier for mission-time constraints."""
        return [cfg for cfg in self.configs.values() if cfg.latency_tier == tier]

    def get_moe_engines(self) -> List[EngineConfig]:
        """Return MoE engines for higher-depth mission reasoning workflows."""
        return [cfg for cfg in self.configs.values() if cfg.is_moe]

    def get_total_storage_required(self, precision: str = "q4") -> float:
        """Sum mission package size by precision for offline deployment planning."""
        normalized_precision = precision.lower()
        if normalized_precision not in {"q4", "fp16"}:
            raise ValueError("precision must be 'q4' or 'fp16'")
        size_field = "q4_size_gb" if normalized_precision == "q4" else "fp16_size_gb"
        return sum(getattr(cfg, size_field) for cfg in self.configs.values())

    def get_capability_score(self, engine_id: EngineID, domain: TaskDomain) -> float:
        """Return domain confidence to support tactical engine arbitration."""
        config = self.get_config(engine_id)
        return config.get_capability_score(domain)

    def get_all_capabilities(self, domain: TaskDomain) -> Dict[str, float]:
        """Get capability scores for all engines in one domain."""
        return {
            config.engine_id.value: config.get_capability_score(domain)
            for config in self.configs.values()
        }

    def get_memory_utilization(self, engines: List[EngineID]) -> float:
        """Get total memory footprint for provided engines."""
        return sum(self.get_config(engine_id).memory_footprint_gb for engine_id in engines)

    def get_total_memory_required(self, engine_ids: List[EngineID]) -> float:
        """Sum VRAM needed to co-load selected engines on edge hardware."""
        return self.get_memory_utilization(engine_ids)
