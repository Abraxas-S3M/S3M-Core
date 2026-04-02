"""
Advanced orchestrator for mission-time multi-engine routing.

This module adds a tactical routing layer on top of the static domain router.
The design is oriented for edge execution where latency, confidence, and audit
traceability must be balanced for operational decision support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Protocol

from .engine_output import StructuredEngineOutput
from .engine_runtime import EngineRuntimeAdapter
from .engine_registry import EngineConfig, EngineID, EngineRegistry, TaskDomain
from .model_registry import ModelRegistry
from .model_optimizer import ModelOptimizer
from .failover_system import FailoverSystem
from .confidence_framework import ConfidenceFramework


LOGGER = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Supported arbitration strategies for the quad-engine fleet."""

    SINGLE_ENGINE = "single_engine"
    CONSENSUS = "consensus"
    HIERARCHICAL = "hierarchical"
    COMPETITIVE = "competitive"
    FALLBACK_CASCADE = "fallback_cascade"
    HYBRID_ADAPTIVE = "hybrid_adaptive"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class UrgencyLevel(Enum):
    """Mission urgency tiers used to adjust aggressiveness of routing."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ReviewStatus(Enum):
    """Review state attached to every synthesized response."""

    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass
class RoutingDecision:
    """Structured decision artifact emitted before execution."""

    selected_engines: List[EngineID]
    strategy: RoutingStrategy
    reason: str
    urgency: UrgencyLevel
    review_required: bool
    confidence_scores: Dict[EngineID, float]


@dataclass
class UnifiedResponse:
    """Normalized response payload from advanced multi-engine arbitration."""

    recommendation_text: str
    normalized_strategy: RoutingStrategy
    confidence_score: float
    review_status: ReviewStatus
    engine_trace: List[EngineID]
    latency_ms: float
    failover_used: bool
    audit_id: str
    raw_outputs: Dict[EngineID, str]


@dataclass
class OrchestratorMetrics:
    """Rolling telemetry used for tactical observability and trend analysis."""

    total_queries: int = 0
    queries_by_strategy: Dict[RoutingStrategy, int] = field(
        default_factory=lambda: {strategy: 0 for strategy in RoutingStrategy}
    )
    avg_latency_ms: float = 0.0
    consensus_agreement_rate: float = 0.0
    engine_success_rates: Dict[EngineID, float] = field(
        default_factory=lambda: {engine_id: 0.0 for engine_id in EngineID}
    )
    routing_accuracy: float = 0.0
    fallback_activations: int = 0
    _latency_ema_alpha: float = 0.2
    _consensus_events: int = 0
    _consensus_agreement_total: float = 0.0
    _routing_hits: int = 0
    _engine_success_counts: Dict[EngineID, int] = field(
        default_factory=lambda: {engine_id: 0 for engine_id in EngineID}
    )
    _engine_total_counts: Dict[EngineID, int] = field(
        default_factory=lambda: {engine_id: 0 for engine_id in EngineID}
    )

    def record_query(
        self,
        *,
        strategy: RoutingStrategy,
        latency_ms: float,
        confidence_score: float,
        review_status: ReviewStatus,
        engine_trace: List[EngineID],
        engine_successes: Dict[EngineID, bool],
        consensus_agreement: Optional[float],
        failover_used: bool,
    ) -> None:
        """Record one routed query and update moving metrics."""
        self.total_queries += 1
        self.queries_by_strategy[strategy] += 1

        if self.total_queries == 1:
            self.avg_latency_ms = latency_ms
        else:
            # EMA keeps mission telemetry responsive to recent performance shifts.
            self.avg_latency_ms = (
                self._latency_ema_alpha * latency_ms
                + (1.0 - self._latency_ema_alpha) * self.avg_latency_ms
            )

        if strategy == RoutingStrategy.CONSENSUS and consensus_agreement is not None:
            self._consensus_events += 1
            self._consensus_agreement_total += consensus_agreement
            self.consensus_agreement_rate = (
                self._consensus_agreement_total / self._consensus_events
            )

        for engine_id in engine_trace:
            self._engine_total_counts[engine_id] += 1
            if engine_successes.get(engine_id, False):
                self._engine_success_counts[engine_id] += 1
            total = self._engine_total_counts[engine_id]
            self.engine_success_rates[engine_id] = (
                self._engine_success_counts[engine_id] / total if total else 0.0
            )

        if confidence_score >= 0.70 and review_status != ReviewStatus.REJECT:
            self._routing_hits += 1
        self.routing_accuracy = (
            self._routing_hits / self.total_queries if self.total_queries else 0.0
        )

        if failover_used:
            self.fallback_activations += 1

    def snapshot(self) -> "OrchestratorMetrics":
        """Return a defensive copy of metrics for API callers."""
        return OrchestratorMetrics(
            total_queries=self.total_queries,
            queries_by_strategy=dict(self.queries_by_strategy),
            avg_latency_ms=self.avg_latency_ms,
            consensus_agreement_rate=self.consensus_agreement_rate,
            engine_success_rates=dict(self.engine_success_rates),
            routing_accuracy=self.routing_accuracy,
            fallback_activations=self.fallback_activations,
            _latency_ema_alpha=self._latency_ema_alpha,
            _consensus_events=self._consensus_events,
            _consensus_agreement_total=self._consensus_agreement_total,
            _routing_hits=self._routing_hits,
            _engine_success_counts=dict(self._engine_success_counts),
            _engine_total_counts=dict(self._engine_total_counts),
        )


class RoutingRequest(Protocol):
    """Protocol for request objects accepted by the advanced router."""

    prompt: str
    domain: Optional[TaskDomain]
    require_consensus: bool
    max_latency_ms: Optional[float]


class AdvancedOrchestrator:
    """Mission-aware orchestrator with adaptive routing and telemetry."""

    TACTICAL_KEYWORDS = frozenset(
        {
            "position",
            "grid",
            "threat",
            "enemy",
            "patrol",
            "sector",
            "contact",
            "movement",
            "strike",
            "target",
            "fire",
            "intel",
            "surveillance",
            "recon",
            "mission",
        }
    )
    REASONING_KEYWORDS = frozenset(
        {
            "analyze",
            "evaluate",
            "assess",
            "compare",
            "why",
            "explain",
            "implications",
            "tradeoff",
            "infer",
            "deduce",
            "reason",
        }
    )
    PLANNING_KEYWORDS = frozenset(
        {
            "plan",
            "schedule",
            "route",
            "logistics",
            "generate",
            "build",
            "create",
            "timeline",
            "allocation",
            "resource",
            "deployment",
        }
    )
    ARABIC_KEYWORDS = frozenset(
        {
            "ما",
            "كيف",
            "أين",
            "متى",
            "لماذا",
            "العربية",
            "عربي",
            "التهديد",
            "خطة",
            "arabic",
        }
    )
    URGENCY_KEYWORDS = {
        UrgencyLevel.CRITICAL: frozenset(
            {
                "critical",
                "urgent",
                "asap",
                "immediate",
                "emergency",
                "priority one",
                "life or death",
            }
        ),
        UrgencyLevel.HIGH: frozenset(
            {
                "high priority",
                "time-sensitive",
                "soon",
                "expedite",
                "rapid",
            }
        ),
        UrgencyLevel.NORMAL: frozenset({"standard", "routine", "normal"}),
        UrgencyLevel.LOW: frozenset({"low priority", "whenever", "later", "defer"}),
    }

    def __init__(
        self,
        registry: Optional[EngineRegistry] = None,
        model_registry: Optional[ModelRegistry] = None,
        optimizer: Optional[ModelOptimizer] = None,
        history_limit: int = 250,
        failover: Optional[FailoverSystem] = None,
    ):
        self.registry = registry or EngineRegistry()
        self.model_registry = model_registry or ModelRegistry(registry=self.registry)
        self.optimizer = optimizer or ModelOptimizer(self.registry)
        self.failover = failover or FailoverSystem()
        self.confidence = ConfidenceFramework()
        self.metrics = OrchestratorMetrics()
        self.history_limit = max(10, history_limit)
        self.routing_history: List[Dict[str, object]] = []
        self._engine_runtime = EngineRuntimeAdapter()

    def execute_with_confidence(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
    ) -> Dict[str, object]:
        """
        Execute request and attach transparent confidence breakdown.

        Tactical context:
        - Confidence gating provides explicit ACCEPT/REVIEW/REJECT posture so
          degraded routing paths cannot silently bypass human oversight.
        """
        result = self.execute_with_failover(prompt=prompt, domain=domain)
        health_snapshot = self.failover.get_health_snapshot()

        selected_engines = [engine.value for engine in result.engine_trace]
        if not selected_engines:
            # Deterministic fallback has no live engine trace but still requires scoring.
            selected_engines = ["deterministic-fallback"]

        engine_health: Dict[str, str] = {}
        for engine_name in selected_engines:
            state = health_snapshot.get(engine_name, {}).get("state", "unknown")
            engine_health[engine_name] = str(state).upper()

        if not result.raw_outputs:
            engine_responses = {selected_engines[0]: result.recommendation_text}
        else:
            engine_responses = {
                engine_id.value: text for engine_id, text in result.raw_outputs.items()
            }

        confidence = self.confidence.score_decision(
            response_text=result.recommendation_text,
            routing_certainty=max(0.0, min(1.0, result.confidence_score)),
            engine_health=engine_health,
            engine_responses=engine_responses,
            selected_engines=selected_engines,
            failover_used=result.failover_used,
            model_drift_detected=False,
            audit_id=result.audit_id,
        )

        return {
            "response": result.recommendation_text,
            "confidence_score": confidence.confidence_score,
            "review_status": confidence.review_status,
            "confidence_factors": confidence.factors.to_dict(),
            "confidence_summary": confidence.summary(),
            "confidence_reasoning": confidence.reasoning,
            "confidence_penalties": confidence.penalties_applied,
            "audit_id": confidence.audit_id,
            "normalized_strategy": result.normalized_strategy.value,
            "engine_trace": selected_engines,
            "latency_ms": result.latency_ms,
            "failover_used": result.failover_used,
        }

    def check_model_integrity(self) -> Dict[str, object]:
        """
        Return integrity snapshot for all registered model artifacts.

        Tactical context:
            Gives mission controllers a lightweight pre-dispatch gate showing
            whether model assets require human review before use.
        """
        status = self.model_registry.list_registry_status(recompute=False)
        return {
            "review_required": status.review_required,
            "status": status.summary(),
            "artifacts": {
                engine_id: {
                    "status": artifact.status,
                    "reason": artifact.drift_reason,
                    "version": artifact.version_tag,
                    "last_verified": artifact.last_verified_at,
                }
                for engine_id, artifact in status.artifacts.items()
            },
        }

    def execute_with_failover(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        require_consensus: bool = False,
        metadata: Optional[Dict[str, object]] = None,
    ) -> UnifiedResponse:
        """
        Execute one query with health-aware routing and deterministic fallback.

        Tactical context:
        - When engines degrade, response posture shifts to REVIEW and deterministic
          safeguards are enforced before any autonomous recommendation is accepted.
        """
        metadata = metadata or {}
        request = SimpleNamespace(
            prompt=prompt,
            domain=domain,
            require_consensus=require_consensus,
            max_latency_ms=metadata.get("max_latency_ms"),
        )

        routed = self.route_and_decide(request)
        healthy_engines = self.failover.get_healthy_engines()

        if not healthy_engines:
            LOGGER.error("All engines unavailable; deterministic fallback activated")
            det = self.failover.get_deterministic_response(
                domain or self._classify_domain(prompt),
                prompt,
            )
            return UnifiedResponse(
                recommendation_text=det.recommendation_text,
                normalized_strategy=RoutingStrategy.DETERMINISTIC_FALLBACK,
                confidence_score=det.confidence_score,
                review_status=self._review_status_from_text(det.review_status),
                engine_trace=[],
                latency_ms=0.0,
                failover_used=True,
                audit_id=det.audit_id,
                raw_outputs={},
            )

        selected = [engine for engine in routed.engine_trace if engine in healthy_engines]
        if selected:
            return routed

        primary = routed.engine_trace[0] if routed.engine_trace else healthy_engines[0]
        fallback = self.failover.choose_fallback(primary, healthy_engines)
        selected = [fallback or healthy_engines[0]]

        audit_id = self.failover.record_failover(
            primary=primary,
            fallbacks_tried=selected,
            succeeded=selected[0],
            reason="Primary route unavailable; fallback selected",
            latency_ms=0.0,
        )
        structured_outputs: Dict[EngineID, StructuredEngineOutput] = self._engine_runtime.execute_engines(
            engine_ids=selected,
            prompt=prompt,
            task_id=f"task-{uuid.uuid4().hex[:8]}",
        )
        raw_outputs = {
            eid: out.raw_text for eid, out in structured_outputs.items()
        }
        return UnifiedResponse(
            recommendation_text=self._build_recommendation(raw_outputs, selected),
            normalized_strategy=RoutingStrategy.FALLBACK_CASCADE,
            confidence_score=max(0.0, min(1.0, routed.confidence_score * 0.9)),
            review_status=ReviewStatus.REVIEW,
            engine_trace=selected,
            latency_ms=routed.latency_ms,
            failover_used=True,
            audit_id=audit_id,
            raw_outputs=raw_outputs,
        )

    def route_and_decide(self, request: RoutingRequest) -> UnifiedResponse:
        """
        Route one request through the adaptive decision tree.

        The method executes the following sequence:
        1) domain + urgency classification,
        2) strategy selection,
        3) weighted engine arbitration,
        4) confidence scoring + review gating,
        5) unified response assembly + audit logging.
        """
        started_at = time.perf_counter()
        prompt = (getattr(request, "prompt", "") or "").strip()
        if not prompt:
            prompt = "status check"

        domain = getattr(request, "domain", None) or self._classify_domain(prompt)
        urgency = self._classify_urgency(prompt)
        strategy = self._select_strategy(request=request, domain=domain, urgency=urgency)
        weights = self._calculate_engine_weights(
            prompt=prompt,
            domain=domain,
            urgency=urgency,
            max_latency_ms=getattr(request, "max_latency_ms", None),
        )
        selected_engines, failover_used = self._select_engines(
            strategy=strategy,
            weights=weights,
            domain=domain,
            request=request,
        )

        confidence_scores = {
            engine_id: self._estimate_confidence(engine_id, domain, weights[engine_id])
            for engine_id in EngineID
        }
        review_required = self._requires_review(
            selected_engines=selected_engines,
            confidence_scores=confidence_scores,
            urgency=urgency,
            strategy=strategy,
        )
        reason = self._explain_strategy(
            strategy=strategy,
            domain=domain,
            urgency=urgency,
            selected_engines=selected_engines,
            request=request,
        )
        decision = RoutingDecision(
            selected_engines=selected_engines,
            strategy=strategy,
            reason=reason,
            urgency=urgency,
            review_required=review_required,
            confidence_scores=confidence_scores,
        )

        structured_outputs: Dict[EngineID, StructuredEngineOutput] = self._engine_runtime.execute_engines(
            engine_ids=selected_engines,
            prompt=prompt,
            task_id=f"task-{uuid.uuid4().hex[:8]}",
        )
        raw_outputs = {
            eid: out.raw_text for eid, out in structured_outputs.items()
        }
        recommendation = self._build_recommendation(raw_outputs, selected_engines)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        latency_ms = max(
            elapsed_ms,
            self._estimate_strategy_latency_ms(
                selected_engines,
                strategy,
                max_latency_ms=getattr(request, "max_latency_ms", None),
            ),
        )

        confidence_score = self._aggregate_confidence(
            selected_engines=selected_engines,
            confidence_scores=confidence_scores,
            strategy=strategy,
        )
        review_status = self._determine_review_status(
            confidence_score=confidence_score,
            review_required=review_required,
            urgency=urgency,
        )
        audit_id = str(uuid.uuid4())
        response = UnifiedResponse(
            recommendation_text=recommendation,
            normalized_strategy=strategy,
            confidence_score=confidence_score,
            review_status=review_status,
            engine_trace=selected_engines,
            latency_ms=latency_ms,
            failover_used=failover_used,
            audit_id=audit_id,
            raw_outputs=raw_outputs,
        )

        consensus_agreement = self._estimate_consensus_agreement(
            strategy=strategy,
            confidence_scores=confidence_scores,
            selected_engines=selected_engines,
        )
        engine_successes = {
            engine_id: confidence_scores.get(engine_id, 0.0) >= 0.55
            for engine_id in selected_engines
        }
        self.metrics.record_query(
            strategy=strategy,
            latency_ms=latency_ms,
            confidence_score=confidence_score,
            review_status=review_status,
            engine_trace=selected_engines,
            engine_successes=engine_successes,
            consensus_agreement=consensus_agreement,
            failover_used=failover_used,
        )
        self._log_routing_decision(
            decision=decision,
            response=response,
            domain=domain,
            prompt=prompt,
        )
        return response

    def _classify_domain(self, prompt: str) -> TaskDomain:
        """Classify request domain by weighted keyword overlap."""
        prompt_lower = prompt.lower()
        scores = {
            TaskDomain.TACTICAL: self._keyword_score(prompt_lower, self.TACTICAL_KEYWORDS),
            TaskDomain.REASONING: self._keyword_score(prompt_lower, self.REASONING_KEYWORDS),
            TaskDomain.PLANNING: self._keyword_score(prompt_lower, self.PLANNING_KEYWORDS),
            TaskDomain.ARABIC_NLP: self._keyword_score(prompt_lower, self.ARABIC_KEYWORDS),
        }
        best_domain = max(scores, key=scores.get)
        if scores[best_domain] <= 0:
            return TaskDomain.TACTICAL
        return best_domain

    def _classify_urgency(self, prompt: str) -> UrgencyLevel:
        """Determine urgency tier from lexical cues and tactical phrasing."""
        prompt_lower = prompt.lower()
        if self._contains_any(prompt_lower, self.URGENCY_KEYWORDS[UrgencyLevel.CRITICAL]):
            return UrgencyLevel.CRITICAL
        if self._contains_any(prompt_lower, self.URGENCY_KEYWORDS[UrgencyLevel.HIGH]):
            return UrgencyLevel.HIGH
        if self._contains_any(prompt_lower, self.URGENCY_KEYWORDS[UrgencyLevel.LOW]):
            return UrgencyLevel.LOW
        if self._contains_any(prompt_lower, self.URGENCY_KEYWORDS[UrgencyLevel.NORMAL]):
            return UrgencyLevel.NORMAL
        return UrgencyLevel.NORMAL

    def _select_strategy(
        self,
        *,
        request: RoutingRequest,
        domain: TaskDomain,
        urgency: UrgencyLevel,
    ) -> RoutingStrategy:
        """Apply the routing decision tree for strategy arbitration."""
        if getattr(request, "require_consensus", False):
            return RoutingStrategy.CONSENSUS

        if urgency == UrgencyLevel.CRITICAL and self._domain_confidence_baseline(domain) >= 0.90:
            return RoutingStrategy.CONSENSUS

        max_latency_ms = getattr(request, "max_latency_ms", None)
        if max_latency_ms is not None and max_latency_ms < 300.0:
            return RoutingStrategy.SINGLE_ENGINE

        if domain == TaskDomain.ARABIC_NLP:
            return RoutingStrategy.SINGLE_ENGINE

        if domain == TaskDomain.REASONING:
            return RoutingStrategy.HIERARCHICAL

        if domain == TaskDomain.PLANNING and urgency in {UrgencyLevel.CRITICAL, UrgencyLevel.HIGH}:
            return RoutingStrategy.COMPETITIVE

        if urgency == UrgencyLevel.LOW:
            return RoutingStrategy.FALLBACK_CASCADE

        if urgency in {UrgencyLevel.CRITICAL, UrgencyLevel.HIGH} and domain == TaskDomain.TACTICAL:
            return RoutingStrategy.HYBRID_ADAPTIVE

        return RoutingStrategy.SINGLE_ENGINE

    def _calculate_engine_weights(
        self,
        *,
        prompt: str,
        domain: TaskDomain,
        urgency: UrgencyLevel,
        max_latency_ms: Optional[float],
    ) -> Dict[EngineID, float]:
        """Compute normalized arbitration weights for each engine."""
        prompt_lower = prompt.lower()
        weights: Dict[EngineID, float] = {engine_id: 1.0 for engine_id in EngineID}

        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            capability = config.capabilities.get(domain, 0.5)
            weights[engine_id] *= 1.0 + (capability * 0.9)

            if config.primary_domain == domain:
                weights[engine_id] *= 1.20

            if urgency == UrgencyLevel.CRITICAL:
                if config.latency_tier == "fast":
                    weights[engine_id] *= 1.30
                else:
                    weights[engine_id] *= 1.08
            elif urgency == UrgencyLevel.HIGH:
                if config.latency_tier in {"fast", "medium"}:
                    weights[engine_id] *= 1.15
            elif urgency == UrgencyLevel.LOW:
                # Low-pressure conditions favor breadth over speed.
                if config.context_window >= 8000:
                    weights[engine_id] *= 1.10

            weights[engine_id] *= 1.0 + self._domain_keyword_boost(
                prompt_lower=prompt_lower,
                domain=domain,
                engine_id=engine_id,
            )

            if max_latency_ms is not None:
                if max_latency_ms < 300.0:
                    if config.latency_tier == "fast":
                        weights[engine_id] *= 1.60
                    else:
                        weights[engine_id] *= 0.70
                elif max_latency_ms < 450.0:
                    if config.latency_tier == "medium":
                        weights[engine_id] *= 1.10

        total = sum(weights.values())
        if total <= 0:
            equal = 1.0 / float(len(EngineID))
            return {engine_id: equal for engine_id in EngineID}
        return {engine_id: value / total for engine_id, value in weights.items()}

    def _select_engines(
        self,
        *,
        strategy: RoutingStrategy,
        weights: Dict[EngineID, float],
        domain: TaskDomain,
        request: RoutingRequest,
    ) -> tuple[List[EngineID], bool]:
        """Select concrete engines based on strategy and arbitration weights."""
        sorted_engines = sorted(weights, key=weights.get, reverse=True)
        failover_used = False
        max_latency_ms = getattr(request, "max_latency_ms", None)

        if strategy == RoutingStrategy.CONSENSUS:
            return list(EngineID), False

        if strategy == RoutingStrategy.SINGLE_ENGINE:
            if domain == TaskDomain.ARABIC_NLP:
                return [EngineID.ALLAM], False
            if max_latency_ms is not None and max_latency_ms < 300.0:
                return [EngineID.PHI3], False
            return [sorted_engines[0]], False

        if strategy == RoutingStrategy.HIERARCHICAL:
            return sorted_engines[:3], False

        if strategy == RoutingStrategy.COMPETITIVE:
            return sorted_engines[:2], False

        if strategy == RoutingStrategy.FALLBACK_CASCADE:
            primary = self.registry.get_engine_for_domain(domain).engine_id
            cascade: List[EngineID] = [primary]
            for engine_id in sorted_engines:
                if engine_id not in cascade:
                    cascade.append(engine_id)
            return cascade, True

        if strategy == RoutingStrategy.HYBRID_ADAPTIVE:
            adaptive = sorted_engines[:2]
            primary = self.registry.get_engine_for_domain(domain).engine_id
            if primary not in adaptive:
                adaptive.append(primary)
            adaptive = adaptive[:3]
            return adaptive, False

        failover_used = True
        return [self.registry.get_engine_for_domain(domain).engine_id], failover_used

    def _estimate_confidence(self, engine_id: EngineID, domain: TaskDomain, weight: float) -> float:
        """Estimate per-engine confidence from capability, prior, and routing weight."""
        config = self.registry.get_config(engine_id)
        capability = config.capabilities.get(domain, 0.5)
        prior = config.confidence_prior
        weighted_boost = min(1.0, weight * 2.0)

        score = (capability * 0.55) + (prior * 0.30) + (weighted_boost * 0.15)
        if config.primary_domain == domain:
            score += 0.05
        return max(0.0, min(0.99, score))

    def _explain_strategy(
        self,
        *,
        strategy: RoutingStrategy,
        domain: TaskDomain,
        urgency: UrgencyLevel,
        selected_engines: List[EngineID],
        request: RoutingRequest,
    ) -> str:
        """Generate a human-readable explanation for auditability."""
        max_latency_ms = getattr(request, "max_latency_ms", None)
        engine_names = ", ".join(engine.value for engine in selected_engines)
        if strategy == RoutingStrategy.CONSENSUS:
            return (
                f"Consensus selected for {urgency.value} {domain.value} workload; "
                f"all engines engaged: {engine_names}."
            )
        if strategy == RoutingStrategy.SINGLE_ENGINE:
            if max_latency_ms is not None:
                return (
                    f"Single-engine routing chosen to satisfy latency budget "
                    f"({max_latency_ms:.0f} ms) with {engine_names}."
                )
            return f"Single-engine routing chosen for efficiency with {engine_names}."
        if strategy == RoutingStrategy.HIERARCHICAL:
            return (
                f"Hierarchical chain chosen for deeper {domain.value} analysis; "
                f"sequence: {engine_names}."
            )
        if strategy == RoutingStrategy.COMPETITIVE:
            return (
                f"Competitive routing chosen to compare top plans under {urgency.value} urgency; "
                f"engines: {engine_names}."
            )
        if strategy == RoutingStrategy.FALLBACK_CASCADE:
            return (
                f"Fallback cascade prepared for resilient execution in {domain.value}; "
                f"order: {engine_names}."
            )
        return (
            f"Hybrid adaptive routing balances speed and confidence for {domain.value}; "
            f"engines: {engine_names}."
        )

    def _log_routing_decision(
        self,
        *,
        decision: RoutingDecision,
        response: UnifiedResponse,
        domain: TaskDomain,
        prompt: str,
    ) -> None:
        """Persist bounded routing history for mission audit traceability."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_id": response.audit_id,
            "domain": domain.value,
            "urgency": decision.urgency.value,
            "strategy": decision.strategy.value,
            "selected_engines": [engine.value for engine in decision.selected_engines],
            "review_required": decision.review_required,
            "review_status": response.review_status.value,
            "confidence_score": response.confidence_score,
            "latency_ms": response.latency_ms,
            "reason": decision.reason,
            "prompt_excerpt": prompt[:160],
            "failover_used": response.failover_used,
        }
        self.routing_history.append(event)
        if len(self.routing_history) > self.history_limit:
            self.routing_history = self.routing_history[-self.history_limit :]
        LOGGER.info(
            "advanced-routing audit_id=%s strategy=%s urgency=%s confidence=%.3f",
            response.audit_id,
            decision.strategy.value,
            decision.urgency.value,
            response.confidence_score,
        )

    def get_metrics(self) -> OrchestratorMetrics:
        """Return current metrics snapshot."""
        return self.metrics.snapshot()

    def get_routing_history(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        """Return recent routing decisions (most recent last)."""
        if limit is None or limit <= 0:
            return list(self.routing_history)
        return list(self.routing_history[-limit:])

    def get_memory_recommendation(self, available_memory_gb: float) -> Dict[str, object]:
        """Get tactical memory and engine recommendations for runtime planning."""
        profile = self.optimizer.recommend_runtime_profile(available_memory_gb)
        return {
            "available_memory_gb": available_memory_gb,
            "recommended_profile": profile,
            "details": self.optimizer.get_profile_details(profile),
        }

    def route_and_decide_structured(self, request) -> Dict[str, Any]:
        """Route request and return structured outputs + reconciliation."""
        # Tactical context: delegate to unified runtime to keep one authoritative
        # mission pipeline for structured state and conflict resolution.
        from .unified_runtime import MissionRequest, UnifiedRuntime

        runtime = UnifiedRuntime()
        result = runtime.execute_mission(
            MissionRequest(
                prompt=getattr(request, "prompt", ""),
                mission_type=getattr(request, "mission_type", "general"),
            )
        )
        return result.to_dict()

    def _build_recommendation(
        self,
        raw_outputs: Dict[EngineID, str],
        selected_engines: List[EngineID],
    ) -> str:
        """Build a unified recommendation text from selected engine outputs."""
        if not selected_engines:
            return "No engine output available."
        primary_engine = selected_engines[0]
        return raw_outputs.get(primary_engine, "No recommendation produced.")

    def _estimate_strategy_latency_ms(
        self,
        selected_engines: List[EngineID],
        strategy: RoutingStrategy,
        max_latency_ms: Optional[float],
    ) -> float:
        """Estimate expected latency envelope for telemetry accounting."""
        if not selected_engines:
            return 0.0
        latencies = [self.registry.get_config(engine_id).inference_latency_ms for engine_id in selected_engines]
        if strategy == RoutingStrategy.SINGLE_ENGINE:
            estimate = min(latencies)
        elif strategy == RoutingStrategy.CONSENSUS:
            estimate = max(latencies) + 12.0
        elif strategy == RoutingStrategy.HIERARCHICAL:
            estimate = sum(latencies) * 0.85
        elif strategy == RoutingStrategy.COMPETITIVE:
            estimate = max(latencies) + 8.0
        elif strategy == RoutingStrategy.FALLBACK_CASCADE:
            estimate = max(latencies) + 15.0
        else:
            estimate = max(latencies) + 10.0

        if max_latency_ms is not None:
            # Cap estimate near the declared mission-time budget.
            estimate = min(estimate, max_latency_ms * 1.10)
        return estimate

    def _aggregate_confidence(
        self,
        *,
        selected_engines: List[EngineID],
        confidence_scores: Dict[EngineID, float],
        strategy: RoutingStrategy,
    ) -> float:
        """Aggregate confidence over selected engines according to strategy semantics."""
        if not selected_engines:
            return 0.0
        values = [confidence_scores[engine_id] for engine_id in selected_engines]
        if strategy == RoutingStrategy.CONSENSUS:
            spread = max(values) - min(values)
            return max(0.0, min(0.99, (sum(values) / len(values)) - (spread * 0.10)))
        if strategy == RoutingStrategy.COMPETITIVE:
            return max(values)
        if strategy == RoutingStrategy.FALLBACK_CASCADE:
            return values[0] * 0.95
        return sum(values) / len(values)

    def _determine_review_status(
        self,
        *,
        confidence_score: float,
        review_required: bool,
        urgency: UrgencyLevel,
    ) -> ReviewStatus:
        """Determine review gate from confidence and urgency posture."""
        if confidence_score < 0.45:
            return ReviewStatus.REJECT
        if review_required:
            return ReviewStatus.REVIEW
        if urgency == UrgencyLevel.CRITICAL and confidence_score < 0.80:
            return ReviewStatus.REVIEW
        if confidence_score < 0.70:
            return ReviewStatus.REVIEW
        return ReviewStatus.ACCEPT

    @staticmethod
    def _review_status_from_text(status: str) -> ReviewStatus:
        """Convert external review string into orchestrator enum."""
        normalized = (status or "").upper()
        if normalized == ReviewStatus.REJECT.value:
            return ReviewStatus.REJECT
        if normalized == ReviewStatus.REVIEW.value:
            return ReviewStatus.REVIEW
        return ReviewStatus.ACCEPT

    def _requires_review(
        self,
        *,
        selected_engines: List[EngineID],
        confidence_scores: Dict[EngineID, float],
        urgency: UrgencyLevel,
        strategy: RoutingStrategy,
    ) -> bool:
        """Compute whether human review should be enforced."""
        if not selected_engines:
            return True
        min_conf = min(confidence_scores[engine_id] for engine_id in selected_engines)
        if min_conf < 0.60:
            return True
        if urgency == UrgencyLevel.CRITICAL and strategy == RoutingStrategy.SINGLE_ENGINE:
            # Critical tactical guidance should avoid single-point model failure.
            return True
        return False

    def _estimate_consensus_agreement(
        self,
        *,
        strategy: RoutingStrategy,
        confidence_scores: Dict[EngineID, float],
        selected_engines: List[EngineID],
    ) -> Optional[float]:
        """Estimate agreement proxy for consensus telemetry."""
        if strategy != RoutingStrategy.CONSENSUS or not selected_engines:
            return None
        values = [confidence_scores[engine_id] for engine_id in selected_engines]
        spread = max(values) - min(values)
        return max(0.0, min(1.0, 1.0 - spread))

    def _domain_confidence_baseline(self, domain: TaskDomain) -> float:
        """Return best available capability for a domain."""
        return max(
            self.registry.get_config(engine_id).capabilities.get(domain, 0.5)
            for engine_id in EngineID
        )

    def _domain_keyword_boost(
        self,
        *,
        prompt_lower: str,
        domain: TaskDomain,
        engine_id: EngineID,
    ) -> float:
        """Return additional boost when prompt strongly matches a domain signal."""
        if domain == TaskDomain.TACTICAL:
            overlap = self._keyword_score(prompt_lower, self.TACTICAL_KEYWORDS)
        elif domain == TaskDomain.REASONING:
            overlap = self._keyword_score(prompt_lower, self.REASONING_KEYWORDS)
        elif domain == TaskDomain.PLANNING:
            overlap = self._keyword_score(prompt_lower, self.PLANNING_KEYWORDS)
        else:
            overlap = self._keyword_score(prompt_lower, self.ARABIC_KEYWORDS)

        config: EngineConfig = self.registry.get_config(engine_id)
        if config.primary_domain == domain:
            return min(0.35, overlap * 0.06)
        return min(0.20, overlap * 0.04)

    @staticmethod
    def _contains_any(prompt_lower: str, keywords: frozenset[str]) -> bool:
        return any(keyword in prompt_lower for keyword in keywords)

    @staticmethod
    def _keyword_score(prompt_lower: str, keywords: frozenset[str]) -> float:
        matches = sum(1 for keyword in keywords if keyword in prompt_lower)
        return float(matches)
