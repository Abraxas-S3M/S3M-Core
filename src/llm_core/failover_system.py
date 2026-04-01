"""
S3M Failover System v1.0
Military-grade resilience with circuit breaker, health tracking, and deterministic fallback.

Design Principles:
  - Defense in Depth (five layers of fallback)
  - Zero Single Points of Failure
  - Graceful Degradation (4 -> 2 -> 1 -> deterministic -> reject)
  - Circuit Breaker Pattern (stop hammering failed engines)
  - Mandatory Review on Degradation
  - Complete Audit Trail
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .engine_registry import EngineID, TaskDomain


logger = logging.getLogger("s3m.failover")


class HealthState(Enum):
    """Engine health states in tactical failover workflow."""

    HEALTHY = "healthy"  # Fully operational
    DEGRADED = "degraded"  # Operational with elevated risk
    UNAVAILABLE = "unavailable"  # Circuit open, execution denied
    WARMING = "warming"  # Half-open, single probe request allowed


class FailoverMode(Enum):
    """System-wide operating posture based on currently available engines."""

    FULL_QUAD = "full_quad"  # 4 engines available
    DUAL_ENGINE = "dual_engine"  # 2-3 engines available
    SINGLE_TACTICAL = "single_tactical"  # 1 engine available
    DETERMINISTIC = "deterministic"  # 0 engines available


# Exponential-decay failure model.
FAILURE_DECAY_LAMBDA = 0.01  # e^(-0.01 * age_seconds)
FAILURE_DECAY_WINDOW_SECONDS = 300  # 5-minute rolling window
FAILURE_TRIP_THRESHOLD = 2.5  # Effective failures to trip circuit
COOLDOWN_SECONDS = 60  # Cooldown before half-open probe
WARMING_REQUEST_TIMEOUT = 5_000  # ms timeout budget during half-open probe

# Rolling request window for success-rate calculation.
SUCCESS_RATE_MAX_REQUESTS = 100
SUCCESS_RATE_WINDOW_SECONDS = 300
SUCCESS_RATE_MIN_SAMPLES = 5

# Deterministic responses by query type.
DETERMINISTIC_RESPONSES: Dict[str, Dict[str, str]] = {
    "tactical": {
        "recommendation_text": (
            "Unable to process tactical query. Human operator review required. "
            "All processing engines currently unavailable."
        ),
        "review_status": "REVIEW",
        "safe_template": (
            "grid:PENDING | status:AWAITING_HUMAN_REVIEW | action:ESCALATE_IMMEDIATE"
        ),
    },
    "reasoning": {
        "recommendation_text": (
            "Unable to perform analysis. System degraded. Human operator review required."
        ),
        "review_status": "REVIEW",
        "safe_template": (
            "analysis:INCOMPLETE | reason:ALL_ENGINES_UNAVAILABLE | escalation:REQUIRED"
        ),
    },
    "planning": {
        "recommendation_text": (
            "Unable to generate operational plan. All engines unavailable. "
            "Human operator review required."
        ),
        "review_status": "REVIEW",
        "safe_template": (
            "mission:ON_HOLD | status:AWAITING_HUMAN_APPROVAL | action:ESCALATE"
        ),
    },
    "arabic_nlp": {
        "recommendation_text": (
            "تعذر معالجة الطلب. جميع محركات المعالجة غير متاحة. مراجعة بشرية مطلوبة."
        ),
        "review_status": "REVIEW",
        "safe_template": (
            "الحالة:قيد_المراجعة_البشرية | الإجراء:تصعيد_فوري | السبب:جميع_المحركات_معطلة"
        ),
    },
    "fallback": {
        "recommendation_text": (
            "System in deterministic fallback mode. All processing engines unavailable. "
            "No automated action possible. Human operator intervention required."
        ),
        "review_status": "REJECT",
        "safe_template": (
            "status:DEGRADED_COMPLETE | action:NONE | escalation:IMMEDIATE_REQUIRED"
        ),
    },
}


@dataclass
class HealthSnapshot:
    """Current health state and recent statistics for one engine."""

    engine_id: EngineID
    state: HealthState
    success_count: int = 0
    failure_count: int = 0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    failure_reason: Optional[str] = None
    success_rate: float = 1.0
    circuit_open_time: Optional[datetime] = None
    warming_test_count: int = 0
    warming_test_passed: bool = False


@dataclass
class FailureEvent:
    """One engine failure in rolling circuit-breaker history."""

    timestamp: datetime
    engine_id: EngineID
    reason: str
    context: Dict[str, Any] = field(default_factory=dict)
    age_in_window: float = 0.0
    weight: float = 1.0

    def update_weight(self, current_time: datetime) -> None:
        """Recalculate weight using exponential time decay."""
        age_seconds = max(0.0, (current_time - self.timestamp).total_seconds())
        self.age_in_window = age_seconds
        self.weight = math.exp(-FAILURE_DECAY_LAMBDA * age_seconds)


@dataclass
class FailoverRecord:
    """Audit record for one failover sequence."""

    audit_id: str
    timestamp: datetime
    primary_engine: EngineID
    fallback_engines_tried: List[EngineID]
    fallback_engines_succeeded: Optional[EngineID]
    final_mode: FailoverMode
    reason: str
    recovery_time_ms: float


@dataclass
class DeterministicResponse:
    """Safe fallback payload returned when model execution is impossible."""

    recommendation_text: str
    review_status: str  # REVIEW or REJECT
    normalized_strategy: str = "DETERMINISTIC_FALLBACK"
    confidence_score: float = 0.0
    engine_trace: List[str] = field(default_factory=list)
    failover_used: bool = True
    audit_id: str = field(default_factory=lambda: str(uuid4()))
    safe_template: str = ""
    all_engines_unavailable: bool = True
    reason: str = "All processing engines unavailable"


@dataclass
class FailureAuditRecord:
    """Granular failure audit entry for forensic mission analysis."""

    audit_id: str
    timestamp: datetime
    engine_id: EngineID
    reason: str
    context: Dict[str, Any]
    resulting_state: HealthState
    effective_failure_count: float


class FailoverSystem:
    """
    Military-grade failover system using circuit-breaker and deterministic fallback.

    Responsibilities:
    1. Track health state of each engine
    2. Maintain rolling-window weighted failures
    3. Open and recover engine circuits
    4. Provide fallback candidates
    5. Emit deterministic safe responses when no execution path is trusted
    6. Persist audit trail for post-mission review
    """

    def __init__(self) -> None:
        """Initialize system health for all registered engines."""
        self.health: Dict[EngineID, HealthSnapshot] = {
            engine_id: HealthSnapshot(engine_id=engine_id, state=HealthState.HEALTHY)
            for engine_id in EngineID
        }
        self.failure_history: Dict[EngineID, List[FailureEvent]] = {
            engine_id: [] for engine_id in EngineID
        }
        self.request_history: Dict[EngineID, List[Tuple[datetime, bool]]] = {
            engine_id: [] for engine_id in EngineID
        }
        self.failover_audit: List[FailoverRecord] = []
        self.failure_audit: List[FailureAuditRecord] = []

        logger.info("FailoverSystem initialized (MIL-SPEC)")

    # ========== PRIMARY API ==========

    def mark_success(self, engine_id: EngineID) -> None:
        """
        Mark an engine request as successful.

        Tactical context:
        - A warming engine that succeeds one controlled probe is considered combat-ready.
        """
        now = datetime.utcnow()
        snapshot = self.health[engine_id]
        snapshot.success_count += 1
        snapshot.last_success_time = now
        self._record_request(engine_id, succeeded=True, at_time=now)

        if snapshot.state == HealthState.WARMING:
            snapshot.warming_test_passed = True
            snapshot.state = HealthState.HEALTHY
            snapshot.success_count = 1
            snapshot.failure_count = 0
            snapshot.failure_reason = None
            snapshot.circuit_open_time = None
            # Tactical doctrine: successful half-open probe restores a clean slate.
            self.failure_history[engine_id] = []
            self.request_history[engine_id] = [(now, True)]
            logger.info("Engine %s recovered from circuit trip", engine_id.value)
        elif snapshot.state == HealthState.UNAVAILABLE and snapshot.circuit_open_time:
            if self._cooldown_elapsed(snapshot):
                snapshot.state = HealthState.HEALTHY
                snapshot.circuit_open_time = None
                snapshot.failure_reason = None

        self._recalculate_success_rate(engine_id)

    def mark_failure(
        self,
        engine_id: EngineID,
        reason: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Mark an engine request as failed and update the circuit state machine.

        Tactical context:
        - Failures are weighted by recency so repeated fresh faults trigger
          immediate disengagement, while stale faults gradually lose influence.
        """
        now = datetime.utcnow()
        payload = context or {}
        snapshot = self.health[engine_id]
        snapshot.failure_count += 1
        snapshot.last_failure_time = now
        snapshot.failure_reason = reason
        self._record_request(engine_id, succeeded=False, at_time=now)

        failure_event = FailureEvent(
            timestamp=now,
            engine_id=engine_id,
            reason=reason,
            context=payload,
        )
        self.failure_history[engine_id].append(failure_event)
        self._cleanup_old_failures(engine_id)

        if snapshot.state == HealthState.WARMING:
            # Tactical doctrine: failed half-open probe immediately re-opens circuit.
            snapshot.state = HealthState.UNAVAILABLE
            snapshot.circuit_open_time = now
            logger.warning(
                "Engine %s warming probe failed; circuit re-opened", engine_id.value
            )
        elif self.should_trip_circuit(engine_id):
            snapshot.state = HealthState.UNAVAILABLE
            snapshot.circuit_open_time = now
            logger.warning(
                "Circuit TRIPPED for %s: %s (effective_failures=%.2f)",
                engine_id.value,
                reason,
                self._get_effective_failure_count(engine_id),
            )
        elif snapshot.state == HealthState.HEALTHY:
            snapshot.state = HealthState.DEGRADED
            logger.warning("Engine %s DEGRADED: %s", engine_id.value, reason)

        self._recalculate_success_rate(engine_id)
        self._record_failure_audit(engine_id, reason=reason, context=payload)

        logger.info(
            "Engine %s failure logged: %s (state=%s)",
            engine_id.value,
            reason,
            snapshot.state.value,
        )

    def get_healthy_engines(self) -> List[EngineID]:
        """
        Return engines currently available for mission routing.

        Included:
        - HEALTHY
        - DEGRADED
        Excluded:
        - WARMING (reserved for controlled probe)
        - UNAVAILABLE (circuit open)
        """
        available: List[EngineID] = []
        for engine_id, snapshot in self.health.items():
            self.should_trip_circuit(engine_id)  # Opportunistically advance cooldown.
            if snapshot.state in {HealthState.HEALTHY, HealthState.DEGRADED}:
                available.append(engine_id)
        return available

    def get_available_engines_by_mode(self) -> Tuple[List[EngineID], FailoverMode]:
        """Return available engines and current failover posture."""
        healthy = self.get_healthy_engines()
        count = len(healthy)
        if count >= 4:
            return healthy, FailoverMode.FULL_QUAD
        if count >= 2:
            return healthy, FailoverMode.DUAL_ENGINE
        if count >= 1:
            return healthy, FailoverMode.SINGLE_TACTICAL
        return healthy, FailoverMode.DETERMINISTIC

    def should_trip_circuit(self, engine_id: EngineID) -> bool:
        """
        Evaluate if the circuit is (or should remain) open for an engine.

        Returns:
            True when execution should be blocked for this engine.
        """
        snapshot = self.health[engine_id]

        if snapshot.state == HealthState.UNAVAILABLE:
            if snapshot.circuit_open_time and self._cooldown_elapsed(snapshot):
                snapshot.state = HealthState.WARMING
                snapshot.warming_test_count += 1
                snapshot.warming_test_passed = False
                logger.info(
                    "Engine %s entered WARMING after cooldown", engine_id.value
                )
                return False
            return True

        if snapshot.state == HealthState.WARMING:
            # Half-open engines are not part of normal routing path.
            return False

        weighted_failures = self._get_effective_failure_count(engine_id)
        should_trip = weighted_failures > FAILURE_TRIP_THRESHOLD
        if should_trip:
            logger.debug(
                "Circuit threshold exceeded for %s: %.2f > %.2f",
                engine_id.value,
                weighted_failures,
                FAILURE_TRIP_THRESHOLD,
            )
        return should_trip

    def choose_fallback(
        self,
        primary_engine: EngineID,
        candidate_engines: List[EngineID],
    ) -> Optional[EngineID]:
        """
        Choose best fallback candidate with deterministic ordering.

        Priority:
          1) Health state (HEALTHY > DEGRADED > WARMING > UNAVAILABLE)
          2) Success rate (higher first)
          3) Last success recency (newer first)
          4) Input order as stable tie-breaker
        """
        available = [engine for engine in candidate_engines if engine != primary_engine]
        if not available:
            return None

        state_priority = {
            HealthState.HEALTHY: 0,
            HealthState.DEGRADED: 1,
            HealthState.WARMING: 2,
            HealthState.UNAVAILABLE: 3,
        }
        rank_index = {engine: idx for idx, engine in enumerate(candidate_engines)}

        def _success_timestamp(engine: EngineID) -> float:
            ts = self.health[engine].last_success_time
            if ts is None:
                return float("-inf")
            return ts.timestamp()

        available.sort(
            key=lambda engine: (
                state_priority[self.health[engine].state],
                -self.health[engine].success_rate,
                -_success_timestamp(engine),
                rank_index.get(engine, 10_000),
            )
        )
        chosen = available[0]
        logger.debug(
            "Fallback chosen: %s from %s",
            chosen.value,
            [engine.value for engine in candidate_engines],
        )
        return chosen

    # ========== DETERMINISTIC FALLBACK ==========

    def get_deterministic_response(
        self,
        domain: TaskDomain,
        original_query: str,
    ) -> DeterministicResponse:
        """
        Build deterministic safe response when no trusted engine is available.

        Tactical context:
        - Output is intentionally non-actionable and always escalates to review.
        """
        template_key = self._domain_to_template_key(domain)
        response_def = DETERMINISTIC_RESPONSES.get(
            template_key, DETERMINISTIC_RESPONSES["fallback"]
        )

        trace = [
            f"{engine_id.value}:{self.health[engine_id].state.value}" for engine_id in EngineID
        ]
        response = DeterministicResponse(
            recommendation_text=response_def["recommendation_text"],
            review_status=response_def["review_status"],
            safe_template=response_def["safe_template"],
            engine_trace=trace,
            audit_id=str(uuid4()),
            reason=(
                "All processing engines unavailable for "
                f"{domain.value}; prompt_length={len(original_query)}"
            ),
        )
        logger.warning(
            "Deterministic fallback triggered domain=%s review=%s",
            domain.value,
            response.review_status,
        )
        return response

    # ========== UTILITY METHODS ==========

    def _cooldown_elapsed(self, snapshot: HealthSnapshot) -> bool:
        """Return True when cooldown timer has elapsed for an unavailable engine."""
        if not snapshot.circuit_open_time:
            return False
        elapsed = (datetime.utcnow() - snapshot.circuit_open_time).total_seconds()
        return elapsed > COOLDOWN_SECONDS

    def _cleanup_old_failures(self, engine_id: EngineID) -> None:
        """Remove failure events outside rolling decay window."""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=FAILURE_DECAY_WINDOW_SECONDS)
        self.failure_history[engine_id] = [
            failure
            for failure in self.failure_history[engine_id]
            if failure.timestamp > window_start
        ]

    def _get_effective_failure_count(self, engine_id: EngineID) -> float:
        """
        Calculate weighted failure count in rolling window.

        Formula:
            sum(exp(-lambda * age_seconds))
        """
        now = datetime.utcnow()
        total_weight = 0.0
        for failure in self.failure_history[engine_id]:
            failure.update_weight(now)
            total_weight += failure.weight
        return total_weight

    def _record_request(self, engine_id: EngineID, succeeded: bool, at_time: datetime) -> None:
        """Record one request outcome for rolling success-rate estimation."""
        events = self.request_history[engine_id]
        events.append((at_time, succeeded))
        self._cleanup_old_requests(engine_id)

    def _cleanup_old_requests(self, engine_id: EngineID) -> None:
        """Keep request history bounded by time window and max sample count."""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=SUCCESS_RATE_WINDOW_SECONDS)
        recent = [(ts, ok) for ts, ok in self.request_history[engine_id] if ts > window_start]
        if len(recent) > SUCCESS_RATE_MAX_REQUESTS:
            recent = recent[-SUCCESS_RATE_MAX_REQUESTS:]
        self.request_history[engine_id] = recent

    def _recalculate_success_rate(self, engine_id: EngineID) -> None:
        """
        Recalculate success-rate in rolling window and update health category.

        Categorization:
          - >=95%  : HEALTHY
          - 80-95% : DEGRADED
          - <80%   : UNAVAILABLE (unless already in WARMING transition)
        """
        snapshot = self.health[engine_id]
        self._cleanup_old_requests(engine_id)
        events = self.request_history[engine_id]

        if not events:
            snapshot.success_rate = 1.0
            return

        successes = sum(1 for _, ok in events if ok)
        snapshot.success_rate = successes / len(events)

        if snapshot.state in {HealthState.UNAVAILABLE, HealthState.WARMING}:
            return

        # Avoid over-escalation on tiny sample sizes (e.g., first failure).
        if len(events) < SUCCESS_RATE_MIN_SAMPLES:
            if snapshot.failure_count > 0 and snapshot.state == HealthState.HEALTHY:
                snapshot.state = HealthState.DEGRADED
            return

        if snapshot.success_rate >= 0.95:
            snapshot.state = HealthState.HEALTHY
        elif snapshot.success_rate >= 0.80:
            snapshot.state = HealthState.DEGRADED
        else:
            # Tactical safeguard: low sustained success blocks autonomous use.
            snapshot.state = HealthState.UNAVAILABLE
            snapshot.circuit_open_time = datetime.utcnow()
            if not snapshot.failure_reason:
                snapshot.failure_reason = "Low success rate in rolling window"

    def _domain_to_template_key(self, domain: TaskDomain) -> str:
        """Map task domain to deterministic response template key."""
        mapping = {
            TaskDomain.TACTICAL: "tactical",
            TaskDomain.REASONING: "reasoning",
            TaskDomain.PLANNING: "planning",
            TaskDomain.ARABIC_NLP: "arabic_nlp",
            TaskDomain.CONSENSUS: "fallback",
        }
        return mapping.get(domain, "fallback")

    def _record_failure_audit(
        self, engine_id: EngineID, reason: str, context: Dict[str, Any]
    ) -> None:
        """Persist one engine-failure audit record."""
        snapshot = self.health[engine_id]
        self.failure_audit.append(
            FailureAuditRecord(
                audit_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                engine_id=engine_id,
                reason=reason,
                context=dict(context),
                resulting_state=snapshot.state,
                effective_failure_count=self._get_effective_failure_count(engine_id),
            )
        )

    # ========== METRICS & AUDIT ==========

    def get_health_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return serializable health snapshot for all engines."""
        report: Dict[str, Dict[str, Any]] = {}
        for engine_id, snapshot in self.health.items():
            report[engine_id.value] = {
                "state": snapshot.state.value,
                "success_rate": f"{snapshot.success_rate:.1%}",
                "success_count": snapshot.success_count,
                "failure_count": snapshot.failure_count,
                "last_success": (
                    snapshot.last_success_time.isoformat()
                    if snapshot.last_success_time
                    else None
                ),
                "last_failure": (
                    snapshot.last_failure_time.isoformat()
                    if snapshot.last_failure_time
                    else None
                ),
                "failure_reason": snapshot.failure_reason,
                "circuit_open_since": (
                    snapshot.circuit_open_time.isoformat()
                    if snapshot.circuit_open_time
                    else None
                ),
                "warming_test_count": snapshot.warming_test_count,
                "warming_test_passed": snapshot.warming_test_passed,
                "effective_failures": round(
                    self._get_effective_failure_count(engine_id), 3
                ),
            }
        return report

    def get_failover_mode(self) -> FailoverMode:
        """Return current system-wide failover mode."""
        _, mode = self.get_available_engines_by_mode()
        return mode

    def record_failover(
        self,
        primary: EngineID,
        fallbacks_tried: List[EngineID],
        succeeded: Optional[EngineID],
        reason: str,
        latency_ms: float,
    ) -> str:
        """Record one failover event in mission audit trail."""
        audit_id = str(uuid4())
        record = FailoverRecord(
            audit_id=audit_id,
            timestamp=datetime.utcnow(),
            primary_engine=primary,
            fallback_engines_tried=list(fallbacks_tried),
            fallback_engines_succeeded=succeeded,
            final_mode=self.get_failover_mode(),
            reason=reason,
            recovery_time_ms=latency_ms,
        )
        self.failover_audit.append(record)
        logger.warning(
            "Failover recorded primary=%s tried=%s succeeded=%s mode=%s latency=%.2fms",
            primary.value,
            [engine.value for engine in fallbacks_tried],
            succeeded.value if succeeded else "NONE",
            record.final_mode.value,
            latency_ms,
        )
        return audit_id

    def get_failover_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent failover events for governance and review boards."""
        bounded_limit = max(1, limit)
        records = self.failover_audit[-bounded_limit:]
        return [
            {
                "audit_id": item.audit_id,
                "timestamp": item.timestamp.isoformat(),
                "primary": item.primary_engine.value,
                "fallbacks_tried": [engine.value for engine in item.fallback_engines_tried],
                "succeeded": (
                    item.fallback_engines_succeeded.value
                    if item.fallback_engines_succeeded
                    else None
                ),
                "mode": item.final_mode.value,
                "reason": item.reason,
                "latency_ms": item.recovery_time_ms,
            }
            for item in records
        ]

    def get_failure_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent engine-failure audit records."""
        bounded_limit = max(1, limit)
        records = self.failure_audit[-bounded_limit:]
        return [
            {
                "audit_id": item.audit_id,
                "timestamp": item.timestamp.isoformat(),
                "engine_id": item.engine_id.value,
                "reason": item.reason,
                "context": dict(item.context),
                "resulting_state": item.resulting_state.value,
                "effective_failure_count": item.effective_failure_count,
            }
            for item in records
        ]

    def reset_engine(self, engine_id: EngineID) -> None:
        """
        Force reset one engine's failover state.

        Tactical context:
        - Intended for controlled operator interventions during maintenance windows.
        """
        self.health[engine_id] = HealthSnapshot(
            engine_id=engine_id,
            state=HealthState.HEALTHY,
        )
        self.failure_history[engine_id] = []
        self.request_history[engine_id] = []
        logger.info("Engine %s failover state reset by operator action", engine_id.value)

    def reset_all(self) -> None:
        """Reset all failover state; used for deterministic unit test setup."""
        for engine_id in EngineID:
            self.reset_engine(engine_id)

