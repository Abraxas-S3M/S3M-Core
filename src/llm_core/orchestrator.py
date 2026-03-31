"""
S3M Quad-Engine Orchestrator
Routes queries to the correct engine or runs consensus across all four.
"""

from typing import Optional, Dict, List
from .engine_registry import EngineRegistry, EngineID, TaskDomain, EngineConfig


class QueryRequest:
    def __init__(self, prompt: str, domain: Optional[TaskDomain] = None, require_consensus: bool = False):
        self.prompt = prompt
        self.domain = domain
        self.require_consensus = require_consensus


class EngineResponse:
    def __init__(self, engine_id: EngineID, text: str, tokens_used: int, latency_ms: float):
        self.engine_id = engine_id
        self.text = text
        self.tokens_used = tokens_used
        self.latency_ms = latency_ms


class ConsensusResult:
    def __init__(self, responses: List[EngineResponse], final_answer: str, agreement_score: float):
        self.responses = responses
        self.final_answer = final_answer
        self.agreement_score = agreement_score


class Orchestrator:
    def __init__(self):
        self.registry = EngineRegistry()
        self.inference_engines: Dict[EngineID, object] = {}

    def classify_domain(self, prompt: str) -> TaskDomain:
        prompt_lower = prompt.lower()
        arabic_keywords = ["ما", "كيف", "أين", "متى", "لماذا", "عربي", "arabic"]
        tactical_keywords = ["position", "grid", "threat", "enemy", "patrol", "sector", "contact", "movement"]
        planning_keywords = ["plan", "schedule", "route", "logistics", "code", "generate", "build", "create"]
        reasoning_keywords = ["analyze", "compare", "evaluate", "assess", "why", "explain", "implications"]
        if any(kw in prompt_lower for kw in arabic_keywords):
            return TaskDomain.ARABIC_NLP
        if any(kw in prompt_lower for kw in tactical_keywords):
            return TaskDomain.TACTICAL
        if any(kw in prompt_lower for kw in planning_keywords):
            return TaskDomain.PLANNING
        if any(kw in prompt_lower for kw in reasoning_keywords):
            return TaskDomain.REASONING
        return TaskDomain.TACTICAL

    def route_query(self, request: QueryRequest) -> EngineConfig:
        if request.domain:
            domain = request.domain
        else:
            domain = self.classify_domain(request.prompt)
        return self.registry.get_engine_for_domain(domain)

    def execute_single(self, request: QueryRequest) -> EngineResponse:
        engine_config = self.route_query(request)
        # Placeholder - will connect to real llama.cpp inference
        return EngineResponse(
            engine_id=engine_config.engine_id,
            text=f"[{engine_config.name}] Response pending - engine not yet loaded",
            tokens_used=0,
            latency_ms=0.0,
        )

    def execute_consensus(self, request: QueryRequest) -> ConsensusResult:
        responses = []
        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            response = EngineResponse(
                engine_id=engine_id,
                text=f"[{config.name}] Consensus response pending",
                tokens_used=0,
                latency_ms=0.0,
            )
            responses.append(response)
        return ConsensusResult(
            responses=responses,
            final_answer="Consensus pending - engines not yet loaded",
            agreement_score=0.0,
        )

    def process(self, request: QueryRequest):
        if request.require_consensus:
            return self.execute_consensus(request)
        return self.execute_single(request)
