"""
S3M LLM Core - Quad-Engine Sovereign AI System
Engines: Phi-3 (Microsoft), Grok (xAI), Mistral (Mistral AI), ALLaM (SDAIA)
"""

from .engine_registry import EngineRegistry, EngineID, TaskDomain, EngineConfig
from .orchestrator import Orchestrator, QueryRequest, EngineResponse, ConsensusResult
from .weight_manager import WeightManager

__all__ = [
    "EngineRegistry", "EngineID", "TaskDomain", "EngineConfig",
    "Orchestrator", "QueryRequest", "EngineResponse", "ConsensusResult",
    "WeightManager",
]
