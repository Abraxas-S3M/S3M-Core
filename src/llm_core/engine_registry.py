"""
S3M Quad-Engine Registry
Four sovereign LLM engines running as one unified system.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum


class EngineID(Enum):
    PHI3 = "phi3-mini"
    GROK = "grok-8b"
    MISTRAL = "mistral-7b"
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


ENGINE_CONFIGS: Dict[EngineID, EngineConfig] = {
    EngineID.PHI3: EngineConfig(
        engine_id=EngineID.PHI3,
        name="Phi-3 Mini",
        provider="Microsoft",
        params="3.8B",
        model_filename="phi-3-mini-4k-instruct-q4_k_m.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="microsoft/Phi-3-mini-4k-instruct-gguf",
        gcs_path="gs://s3m-weight-vault/phi3/phi-3-mini-4k-instruct-q4_k_m.gguf",
        local_path="models/phi3/phi-3-mini-4k-instruct-q4_k_m.gguf",
        max_tokens=512,
        context_window=4096,
        primary_domain=TaskDomain.TACTICAL,
    ),
    EngineID.GROK: EngineConfig(
        engine_id=EngineID.GROK,
        name="Grok",
        provider="xAI",
        params="8B",
        model_filename="grok-8b-q4_k_m.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="xai-org/grok-1",
        gcs_path="gs://s3m-weight-vault/grok/grok-8b-q4_k_m.gguf",
        local_path="models/grok/grok-8b-q4_k_m.gguf",
        max_tokens=1024,
        context_window=8192,
        primary_domain=TaskDomain.REASONING,
    ),
    EngineID.MISTRAL: EngineConfig(
        engine_id=EngineID.MISTRAL,
        name="Mistral 7B",
        provider="Mistral AI",
        params="7B",
        model_filename="mistral-7b-instruct-v0.3-q4_k_m.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="mistralai/Mistral-7B-Instruct-v0.3",
        gcs_path="gs://s3m-weight-vault/mistral/mistral-7b-instruct-v0.3-q4_k_m.gguf",
        local_path="models/mistral/mistral-7b-instruct-v0.3-q4_k_m.gguf",
        max_tokens=1024,
        context_window=32768,
        primary_domain=TaskDomain.PLANNING,
    ),
    EngineID.ALLAM: EngineConfig(
        engine_id=EngineID.ALLAM,
        name="ALLaM-7B",
        provider="SDAIA",
        params="7B",
        model_filename="allam-7b-q4_k_m.gguf",
        quantization="Q4_K_M",
        runtime="llama.cpp",
        hf_repo="sdaia/allam-7b",
        gcs_path="gs://s3m-weight-vault/allam/allam-7b-q4_k_m.gguf",
        local_path="models/allam/allam-7b-q4_k_m.gguf",
        max_tokens=1024,
        context_window=4096,
        primary_domain=TaskDomain.ARABIC_NLP,
    ),
}


DOMAIN_ROUTING = {
    TaskDomain.TACTICAL: EngineID.PHI3,
    TaskDomain.REASONING: EngineID.GROK,
    TaskDomain.PLANNING: EngineID.MISTRAL,
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
