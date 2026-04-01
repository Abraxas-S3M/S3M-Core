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
from .consensus_engine import (
    ConsensusEngine,
    ConsensusMode,
    ConsensusResult,
    EngineResponse as ConsensusEngineResponse,
    AgreementLevel,
)
from .weight_manager import WeightManager
from .inference_engine import InferenceEngine, InferenceResult
from .engine_pool import EnginePool
from .tactical_prompts import get_system_prompt, DOMAIN_PROMPTS
from .session import S3MSession

__all__ = [
    "EngineRegistry", "EngineID", "TaskDomain", "EngineConfig",
    "Orchestrator", "QueryRequest", "OrchestratorEngineResponse", "OrchestratorConsensusResult",
    "WeightManager",
    "InferenceEngine", "InferenceResult",
    "EnginePool",
    "get_system_prompt", "DOMAIN_PROMPTS",
    "S3MSession",
    "ConsensusEngine",
    "ConsensusMode",
    "ConsensusResult",
    "ConsensusEngineResponse",
    "AgreementLevel",
]
