"""
S3M LLM Core - Quad-Engine Sovereign AI System
Phase 3: Live inference via llama-cpp-python
Engines: Phi-3 (Microsoft), Grok (xAI), Mistral (Mistral AI), ALLaM (SDAIA)
"""

from .engine_registry import EngineRegistry, EngineID, TaskDomain, EngineConfig
from .orchestrator import Orchestrator, QueryRequest, EngineResponse, ConsensusResult
from .advanced_orchestrator import (
    AdvancedOrchestrator,
    RoutingStrategy,
    RoutingDecision,
    UnifiedResponse,
    OrchestratorMetrics,
    UrgencyLevel,
)
from .failover_system import (
    FailoverSystem,
    HealthState,
    FailoverMode,
    DeterministicResponse,
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

__all__ = [
    "EngineRegistry", "EngineID", "TaskDomain", "EngineConfig",
    "Orchestrator", "QueryRequest", "EngineResponse", "ConsensusResult",
    "AdvancedOrchestrator", "RoutingStrategy", "RoutingDecision",
    "UnifiedResponse", "OrchestratorMetrics", "UrgencyLevel",
    "FailoverSystem", "HealthState", "FailoverMode", "DeterministicResponse",
    "WeightManager",
    "InferenceEngine", "InferenceResult",
    "EnginePool",
    "PredictivePreloader", "RequestRecord", "EngineScore", "PreloadPrediction", "PreloadPlan",
    "get_system_prompt", "DOMAIN_PROMPTS",
    "S3MSession",
]
