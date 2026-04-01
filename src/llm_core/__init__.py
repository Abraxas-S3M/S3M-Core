"""
S3M LLM Core - Quad-Engine Sovereign AI System
Phase 3: Live inference via llama-cpp-python
Engines: Phi-3 (Microsoft), Grok (xAI), Mistral (Mistral AI), ALLaM (SDAIA)
"""

from .engine_registry import EngineRegistry, EngineID, TaskDomain, EngineConfig
from .orchestrator import (
    Orchestrator,
    QueryRequest,
    EngineResponse as OrchestratorEngineResponse,
    ConsensusResult as OrchestratorConsensusResult,
)
from .advanced_orchestrator import (
    AdvancedOrchestrator,
    RoutingStrategy,
    RoutingDecision,
    UnifiedResponse,
    OrchestratorMetrics,
    UrgencyLevel,
)
from .model_registry import ModelRegistry, ModelArtifact, RegistryStatus
from .model_optimizer import (
    AllocationPlan,
    HARDWARE_PROFILES,
    HardwareProfile,
    LoadCategory,
    MemoryBudget,
    ModelOptimizer,
    ModelProfile,
    PreloadPlan,
    RUNTIME_PROFILES,
    RuntimeProfile,
    estimate_inference_time,
)
from .failover_system import (
    FailoverSystem,
    HealthState,
    FailoverMode,
    DeterministicResponse,
)
from .consensus_engine import (
    ConsensusEngine,
    ConsensusMode,
    ConsensusResult as ConsensusEngineResult,
    EngineResponse as ConsensusEngineResponse,
    AgreementLevel,
)
from .weight_manager import WeightManager
from .inference_engine import InferenceEngine, InferenceResult
from .engine_pool import EnginePool
from .predictive_preload import (
    PredictivePreloader,
    RequestRecord,
    EngineScore,
    PreloadPrediction,
    PreloadPlan,
)
from .tactical_prompts import get_system_prompt, DOMAIN_PROMPTS
from .session import S3MSession

# Backward-compatible aliases from legacy orchestrator API surface.
EngineResponse = OrchestratorEngineResponse
ConsensusResult = OrchestratorConsensusResult

__all__ = [
    "EngineRegistry", "EngineID", "TaskDomain", "EngineConfig",
    "Orchestrator", "QueryRequest", "EngineResponse", "ConsensusResult",
    "OrchestratorEngineResponse", "OrchestratorConsensusResult",
    "AdvancedOrchestrator", "RoutingStrategy", "RoutingDecision",
    "UnifiedResponse", "OrchestratorMetrics", "UrgencyLevel",
    "ModelRegistry", "ModelArtifact", "RegistryStatus",
    "ModelOptimizer", "ModelProfile", "AllocationPlan", "PreloadPlan",
    "MemoryBudget", "LoadCategory", "HardwareProfile", "RuntimeProfile",
    "HARDWARE_PROFILES", "RUNTIME_PROFILES", "estimate_inference_time",
    "FailoverSystem", "HealthState", "FailoverMode", "DeterministicResponse",
    "WeightManager",
    "InferenceEngine", "InferenceResult",
    "EnginePool",
    "PredictivePreloader", "RequestRecord", "EngineScore", "PreloadPrediction", "PreloadPlan",
    "get_system_prompt", "DOMAIN_PROMPTS",
    "S3MSession",
    "ConsensusEngine",
    "ConsensusMode",
    "ConsensusEngineResult",
    "ConsensusEngineResponse",
    "AgreementLevel",
]
