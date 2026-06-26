"""S3M-Core Quad-Engine Orchestration Demo Layer.

Tactical context:
    This package is the first functional quad-engine AI orchestration demo for
    S3M-Core. It receives an operational packet (COP track update, alert, feed
    message, decision request, or operator note), classifies and routes it,
    consults four advisory reasoning engines (tactical, reasoning, planning,
    Arabic), and returns a structured, commander-ready brief to S3M-GUI.

Safety doctrine (enforced throughout this package):
    * Demo orchestration only -- it never starts model training, the trainer,
      or the sync daemon, never launches RunPod, and never calls Grok/xAI.
    * No external API calls; the only optional inference is a guarded local
      llama.cpp subprocess, disabled unless ``S3M_ENABLE_LOCAL_LLM=true``.
    * No R2 credentials, model paths, or vault storage are exposed to the GUI.
    * All outputs are recommendations / briefs / summaries; every result is
      ``human_review_required`` and no autonomous kinetic action is implemented.
"""

from src.quad_engine.audit_log import AuditLog, get_audit_log
from src.quad_engine.local_llm import LocalLLMRunner, get_local_llm
from src.quad_engine.model_registry import (
    ModelRegistry,
    get_registry,
    local_llm_enabled,
)
from src.quad_engine.models import (
    ARABIC_ENGINE,
    ENGINE_IDS,
    PLANNING_ENGINE,
    REASONING_ENGINE,
    TACTICAL_ENGINE,
    CoaOption,
    DecisionCard,
    EngineRecord,
    EngineRole,
    EngineStatus,
    ModelRegistryEntry,
    OperationalPacket,
    OrchestratorStatus,
    PacketType,
    QuadEngineResult,
    RouteInfo,
)
from src.quad_engine.orchestrator import QuadEngineOrchestrator, get_orchestrator
from src.quad_engine.packet_router import PacketRouter, get_packet_router
from src.quad_engine.routes import router as quad_engine_router

__all__ = [
    "AuditLog",
    "get_audit_log",
    "LocalLLMRunner",
    "get_local_llm",
    "ModelRegistry",
    "get_registry",
    "local_llm_enabled",
    "ModelRegistryEntry",
    "EngineRecord",
    "EngineRole",
    "EngineStatus",
    "PacketType",
    "OperationalPacket",
    "OrchestratorStatus",
    "QuadEngineResult",
    "RouteInfo",
    "DecisionCard",
    "CoaOption",
    "ENGINE_IDS",
    "TACTICAL_ENGINE",
    "REASONING_ENGINE",
    "PLANNING_ENGINE",
    "ARABIC_ENGINE",
    "QuadEngineOrchestrator",
    "get_orchestrator",
    "PacketRouter",
    "get_packet_router",
    "quad_engine_router",
]
