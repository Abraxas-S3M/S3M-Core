"""
S3M Orchestrator v2.0
Facade pattern: delegates to AdvancedOrchestrator.

Backward compatible with existing imports:
  from s3m_core import Orchestrator
  orch = Orchestrator()
  result = orch.route_and_decide(prompt)  # Still works

Advanced features available:
  result = orch.execute_with_confidence(prompt)
  result = orch.route_with_failover(prompt)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .advanced_orchestrator import (
    AdvancedOrchestrator,
    RoutingDecision,
    RoutingStrategy,
    UnifiedResponse,
    UrgencyLevel,
)
from .confidence_framework import ConfidenceFramework
from .consensus_engine import ConsensusEngine, EngineResponse as ConsensusEngineResponse
from .engine_registry import EngineConfig, EngineID, EngineRegistry, TaskDomain
from .failover_system import FailoverSystem
from .model_optimizer import ModelOptimizer
from .model_registry import ModelRegistry
from .predictive_preload import PredictivePreloader


logger = logging.getLogger("s3m.orchestrator")


@dataclass
class QueryRequest:
    """Legacy request format maintained for backward compatibility."""

    prompt: str
    domain: Optional[TaskDomain] = None
    require_consensus: bool = False
    max_latency_ms: Optional[float] = None
    time_budget_ms: float = 10000.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EngineResponse:
    """Legacy response format maintained for backward compatibility."""

    engine_id: EngineID
    text: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    success: bool = True


@dataclass
class ConsensusResult:
    """Legacy consensus format maintained for backward compatibility."""

    responses: List[EngineResponse]
    synthesis: str
    agreement_score: float
    audit_id: str

    @property
    def final_answer(self) -> str:
        # Backward-compat alias retained for legacy callers.
        return self.synthesis


class Orchestrator:
    """
    S3M Orchestrator v2.0 facade.

    Tactical context:
    This class keeps legacy methods operational while exposing richer confidence,
    failover, preload, and integrity APIs required for mission-time oversight.
    """

    def __init__(
        self,
        registry: Optional[EngineRegistry] = None,
        advanced_orch: Optional[AdvancedOrchestrator] = None,
    ) -> None:
        self.registry = registry or EngineRegistry()
        self.inference_engines: Dict[EngineID, object] = {}
        self.consensus_engine = ConsensusEngine()
        self.advanced_orch = advanced_orch or AdvancedOrchestrator(registry=self.registry)
        self._advanced_orchestrator = self.advanced_orch

        # Shared systems exposed for dashboard and tactical observability hooks.
        self.failover = getattr(self.advanced_orch, "failover", FailoverSystem())
        self.optimizer = getattr(self.advanced_orch, "optimizer", ModelOptimizer(self.registry))
        self.preloader = getattr(self.advanced_orch, "preloader", PredictivePreloader(self.registry))
        self.model_registry = getattr(
            self.advanced_orch,
            "model_registry",
            ModelRegistry(registry=self.registry),
        )
        self.confidence = getattr(self.advanced_orch, "confidence", ConfidenceFramework())

        # Ensure advanced orchestrator exposes integrated systems for callers
        # that access advanced_orch directly during tactical diagnostics.
        self.advanced_orch.failover = self.failover
        self.advanced_orch.optimizer = self.optimizer
        self.advanced_orch.preloader = self.preloader
        self.advanced_orch.model_registry = self.model_registry
        self.advanced_orch.confidence = self.confidence
        logger.info("Orchestrator v2.0 initialized (facade mode)")

    # ========== Backward-compatible v1 methods ==========
    def classify_domain(self, prompt: str) -> TaskDomain:
        prompt_lower = (prompt or "").lower()
        arabic_keywords = {"ما", "كيف", "أين", "متى", "لماذا", "عربي", "arabic"}
        tactical_keywords = {
            "position",
            "grid",
            "threat",
            "enemy",
            "patrol",
            "sector",
            "contact",
            "movement",
        }
        planning_keywords = {"plan", "schedule", "route", "logistics", "code", "generate", "build", "create"}
        reasoning_keywords = {"analyze", "compare", "evaluate", "assess", "why", "explain", "implications"}
        if any(keyword in prompt_lower for keyword in arabic_keywords):
            return TaskDomain.ARABIC_NLP

        # Tactical context: mixed prompts should prefer the strongest semantic
        # signal rather than first-match ordering to avoid misrouting analysis tasks.
        scores = {
            TaskDomain.TACTICAL: sum(1 for keyword in tactical_keywords if keyword in prompt_lower),
            TaskDomain.REASONING: sum(1 for keyword in reasoning_keywords if keyword in prompt_lower),
            TaskDomain.PLANNING: sum(1 for keyword in planning_keywords if keyword in prompt_lower),
        }
        if max(scores.values()) <= 0:
            return TaskDomain.TACTICAL
        priority = {
            TaskDomain.REASONING: 3,
            TaskDomain.PLANNING: 2,
            TaskDomain.TACTICAL: 1,
        }
        return max(scores, key=lambda domain: (scores[domain], priority[domain]))

    def route_query(self, request: QueryRequest) -> EngineConfig:
        domain = request.domain or self.classify_domain(request.prompt)
        return self.registry.get_engine_for_domain(domain)

    def execute_single(self, request: QueryRequest) -> EngineResponse:
        engine_config = self.route_query(request)
        return EngineResponse(
            engine_id=engine_config.engine_id,
            text=f"[{engine_config.name}] Response pending - engine not yet loaded",
            tokens_used=0,
            latency_ms=0.0,
            success=True,
        )

    def execute_consensus(self, request: QueryRequest) -> ConsensusResult:
        responses: List[EngineResponse] = []
        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            responses.append(
                EngineResponse(
                    engine_id=engine_id,
                    text=f"[{config.name}] Consensus route initialized - engine not loaded",
                    tokens_used=0,
                    latency_ms=0.0,
                    success=True,
                )
            )
        return ConsensusResult(
            responses=responses,
            synthesis="Consensus route initialized - engines not yet loaded",
            agreement_score=0.0,
            audit_id=str(uuid4()),
        )

    def process(self, request: QueryRequest) -> Any:
        if request.require_consensus:
            return self.execute_consensus(request)
        return self.execute_single(request)

    def synthesize_consensus(self, engine_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesize consensus from response dictionaries."""
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
        """Advanced routing envelope with confidence and audit trace."""
        return self.advanced_orch.route_and_decide(request)

    def get_advanced_metrics(self) -> Dict[str, Any]:
        """Expose adaptive routing telemetry for operational dashboards."""
        metrics = self.advanced_orch.get_metrics()
        return {
            "total_queries": metrics.total_queries,
            "avg_latency_ms": metrics.avg_latency_ms,
            "consensus_agreement_rate": metrics.consensus_agreement_rate,
            "routing_accuracy": metrics.routing_accuracy,
            "fallback_activations": metrics.fallback_activations,
            "queries_by_strategy": {
                strategy.value: count for strategy, count in metrics.queries_by_strategy.items()
            },
            "engine_success_rates": {
                engine_id.value: rate for engine_id, rate in metrics.engine_success_rates.items()
            },
        }

    def get_routing_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Expose recent advanced routing decisions for audit review."""
        return self.advanced_orch.get_routing_history(limit=limit)

    # ========== Facade v2 methods ==========
    def route_and_decide(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        require_consensus: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        time_budget_ms: float = 10000.0,
    ) -> Dict[str, Any]:
        """Legacy-compatible route and decide API returning a dictionary payload."""
        max_latency_ms = None
        if isinstance(metadata, dict):
            value = metadata.get("max_latency_ms")
            if isinstance(value, (int, float)):
                max_latency_ms = float(value)
        if max_latency_ms is None and isinstance(time_budget_ms, (int, float)) and time_budget_ms > 0:
            max_latency_ms = float(time_budget_ms)

        request = QueryRequest(
            prompt=prompt,
            domain=domain,
            require_consensus=require_consensus,
            max_latency_ms=max_latency_ms,
            time_budget_ms=float(time_budget_ms),
            metadata=metadata or {},
        )
        decision = self.advanced_orch.route_and_decide(request)

        selected_engines = list(decision.engine_trace)
        confidence_scores = {
            engine_id: round(float(decision.confidence_score), 4) for engine_id in selected_engines
        }
        return {
            "recommendation_text": decision.recommendation_text,
            "strategy": decision.normalized_strategy.value,
            "selected_engines": selected_engines,
            "confidence_scores": confidence_scores,
            "review_required": decision.review_status.value != "ACCEPT",
            "latency_ms": decision.latency_ms,
            "audit_id": decision.audit_id,
            "failover_used": decision.failover_used,
        }

    def execute_with_confidence(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute with confidence scoring and operator-facing rationale."""
        routed = self.route_and_decide(
            prompt=prompt,
            domain=domain,
            metadata=metadata,
            require_consensus=False,
        )
        selected_engines: List[EngineID] = list(routed.get("selected_engines", []))
        health_snapshot = self.failover.get_health_snapshot()

        engine_responses: Dict[str, str] = {}
        for engine_id in selected_engines:
            engine_responses[engine_id.value] = str(routed["recommendation_text"])[:200]

        engine_health: Dict[str, str] = {}
        for engine_id in selected_engines:
            record = health_snapshot.get(engine_id.value, {})
            state = str(record.get("state", "unknown"))
            engine_health[engine_id.value] = state.upper()

        drift_detected = False
        for engine_id in selected_engines:
            verification = self.model_registry.verify_artifact(engine_id)
            if isinstance(verification, tuple):
                is_clean = bool(verification[0])
                status = str(verification[1]) if len(verification) > 1 else "UNKNOWN"
            else:
                is_clean = str(getattr(verification, "status", "UNKNOWN")).upper() == "CLEAN"
                status = str(getattr(verification, "status", "UNKNOWN"))
            if (not is_clean) and status.upper() != "UNKNOWN":
                drift_detected = True
                break

        confidence = self.confidence.score_decision(
            response_text=str(routed["recommendation_text"]),
            routing_certainty=0.85,
            engine_health=engine_health,
            engine_responses=engine_responses,
            selected_engines=[engine.value for engine in selected_engines],
            failover_used=bool(routed.get("failover_used", False)),
            model_drift_detected=drift_detected,
            audit_id=str(routed.get("audit_id", "unknown")),
        )

        return {
            "recommendation_text": routed["recommendation_text"],
            "strategy": routed["strategy"],
            "selected_engines": [engine.value for engine in selected_engines],
            "confidence_score": round(confidence.confidence_score, 4),
            "review_status": confidence.review_status,
            "confidence_factors": confidence.factors.to_dict(),
            "confidence_reasoning": list(confidence.reasoning),
            "confidence_penalties": list(confidence.penalties_applied),
            "audit_id": routed["audit_id"],
            "latency_ms": routed["latency_ms"],
            "failover_used": bool(routed.get("failover_used", False)),
            "model_drift_detected": drift_detected,
        }

    def route_with_failover(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
    ) -> Dict[str, Any]:
        """Route with explicit failover visibility for tactical observability."""
        decision = self.route_and_decide(prompt=prompt, domain=domain)
        selected_engines: List[EngineID] = list(decision.get("selected_engines", []))
        health = self.failover.get_health_snapshot()

        if bool(decision.get("failover_used", False)):
            healthy_engines = [
                engine_id
                for engine_id, state in health.items()
                if isinstance(state, dict) and str(state.get("state", "")).lower() == "healthy"
            ]
            unavailable_engines = [
                engine_id
                for engine_id, state in health.items()
                if isinstance(state, dict) and str(state.get("state", "")).lower() == "unavailable"
            ]
        else:
            healthy_engines = [engine.value for engine in selected_engines]
            unavailable_engines = []

        return {
            "recommendation_text": decision["recommendation_text"],
            "selected_engines": [engine.value for engine in selected_engines],
            "failover_used": bool(decision.get("failover_used", False)),
            "healthy_engines": healthy_engines,
            "unavailable_engines": unavailable_engines,
            "audit_id": decision["audit_id"],
        }

    def predict_next_engines(
        self,
        domain_hint: Optional[TaskDomain] = None,
        limit: int = 2,
    ) -> Dict[str, Any]:
        """Predict likely next engines for warmup planning."""
        prediction = self.preloader.predict_next_engines(domain_hint=domain_hint, limit=limit)
        return {
            "predicted_engines": [engine.value for engine in prediction.predicted_engines],
            "confidence": prediction.confidence,
            "reasoning": prediction.reasoning,
            "recommendation": prediction.recommendation,
        }

    def check_system_health(self) -> Dict[str, Any]:
        """Return consolidated model, engine, and failover status."""
        model_status = self.model_registry.list_registry_status(recompute=False)
        health_snapshot = self.failover.get_health_snapshot()

        issues: List[str] = []
        if model_status.missing_artifacts > 0:
            issues.append(f"Missing models: {model_status.missing_artifacts}")
        if model_status.mismatched_artifacts > 0:
            issues.append(f"Model hash mismatches: {model_status.mismatched_artifacts}")
        if model_status.stale_artifacts > 0:
            issues.append(f"Stale verifications: {model_status.stale_artifacts}")

        unavailable_engines = [
            engine_id
            for engine_id, state in health_snapshot.items()
            if isinstance(state, dict) and str(state.get("state", "")).lower() == "unavailable"
        ]
        if unavailable_engines:
            issues.append(f"Unavailable engines: {unavailable_engines}")

        overall_status = "DEGRADED" if issues else "HEALTHY"
        engines = {}
        for engine_id, state in health_snapshot.items():
            if not isinstance(state, dict):
                continue
            engines[engine_id] = {
                "state": state.get("state"),
                "success_rate": state.get("success_rate"),
                "last_success_time": state.get("last_success_time") or state.get("last_success"),
                "last_failure_time": state.get("last_failure_time") or state.get("last_failure"),
            }

        return {
            "overall_status": overall_status,
            "models": {
                "total": model_status.total_artifacts,
                "clean": model_status.clean_artifacts,
                "missing": model_status.missing_artifacts,
                "mismatched": model_status.mismatched_artifacts,
                "stale": model_status.stale_artifacts,
                "review_required": model_status.review_required,
            },
            "engines": engines,
            "failover": {
                "system_operational": True,
                "circuit_breakers_open": len(unavailable_engines),
            },
            "issues": issues,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_system_recommendations(self) -> Dict[str, Any]:
        """Get operator guidance for resource loading and maintenance."""
        allocation = self.optimizer.allocate_for_hardware(hardware_profile="edge_64gb")
        preload_prediction = self.preloader.predict_next_engines()
        health = self.check_system_health()
        return {
            "resource_allocation": {
                "recommended_profile": allocation.runtime_profile,
                "engines_to_load": [engine.value for engine in allocation.allocated_engines],
                "expected_latency_ms": allocation.expected_latency_ms,
                "consensus_available": allocation.consensus_available,
            },
            "preload_suggestion": {
                "engines": [engine.value for engine in preload_prediction.predicted_engines],
                "confidence": preload_prediction.confidence,
            },
            "maintenance_alerts": health["issues"],
        }
