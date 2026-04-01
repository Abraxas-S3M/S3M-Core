"""
S3M Quad-Engine Orchestrator
Routes queries to the correct engine or runs consensus across all four.
"""

from typing import Optional, Dict, List, Any
from .advanced_orchestrator import AdvancedOrchestrator, UnifiedResponse
from .engine_registry import EngineRegistry, EngineID, TaskDomain, EngineConfig
from .consensus_engine import ConsensusEngine, EngineResponse as ConsensusEngineResponse


class QueryRequest:
    def __init__(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        require_consensus: bool = False,
        max_latency_ms: Optional[float] = None,
    ):
        self.prompt = prompt
        self.domain = domain
        self.require_consensus = require_consensus
        self.max_latency_ms = max_latency_ms


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
        self.consensus_engine = ConsensusEngine()
        self._advanced_orchestrator = AdvancedOrchestrator(registry=self.registry)

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

    def synthesize_consensus(self, engine_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synthesize consensus from multiple engine responses.

        Args:
            engine_responses: List of response dictionaries.

        Returns:
            Dictionary representation of ConsensusResult.
        """
        consensus_inputs: List[ConsensusEngineResponse] = []
        for response in engine_responses:
            raw_engine_id = response["engine_id"]
            engine_id = raw_engine_id.value if hasattr(raw_engine_id, "value") else str(raw_engine_id)
            raw_confidence = response.get("confidence_score", 0.75)
            confidence_score = None if raw_confidence is None else float(raw_confidence)
            consensus_inputs.append(
                ConsensusEngineResponse(
                    engine_id=engine_id,
                    text=str(response["text"]),
                    latency_ms=float(response.get("latency_ms", 0.0)),
                    tokens_generated=int(response.get("tokens", response.get("tokens_generated", 0))),
                    confidence_score=confidence_score,
                    failed=bool(response.get("failed", False)),
                    error_message=response.get("error_message"),
                )
            )

        result = self.consensus_engine.synthesize(consensus_inputs)
        return result.to_dict()

    def route_advanced(self, request: QueryRequest) -> UnifiedResponse:
        """
        Advanced mission-aware routing path with confidence and audit trace.

        This does not change the legacy process() behavior so existing modules
        can continue using the original routing interface without regressions.
        """
        return self._advanced_orchestrator.route_and_decide(request)

    def get_advanced_metrics(self):
        """Expose adaptive routing telemetry for operational dashboards."""
        return self._advanced_orchestrator.get_metrics()

    def get_routing_history(self, limit: Optional[int] = None):
        """Expose recent advanced routing decisions for audit review."""
        return self._advanced_orchestrator.get_routing_history(limit=limit)
