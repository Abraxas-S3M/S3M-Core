"""
S3M Predictive Preloader v1.0
Intelligent engine preloading based on deterministic usage forecasting.

This module is intentionally offline and deterministic for sovereign edge
deployment on Jetson hardware in contested environments.

Operational questions answered:
  • Which engines are likely to be needed next?
  • Should those engines be warmed before the next tactical query?
  • How confident is the forecast?

Forecast algorithm:
  final_score = (0.4 * recency) + (0.4 * frequency) + (0.2 * domain_affinity)
where:
  recency = exp(-lambda * seconds_since_last_use)
  frequency = uses_in_window / total_requests_in_window
  domain_affinity = EngineRegistry capability score for target domain
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .engine_registry import EngineID, EngineRegistry, TaskDomain

logger = logging.getLogger("s3m.preloader")


# Configuration constants
RECENCY_DECAY_LAMBDA = 0.01
RECENCY_WINDOW_SECONDS = 300
MAX_HISTORY_SIZE = 100

# Scoring weights (must sum to 1.0)
WEIGHT_RECENCY = 0.4
WEIGHT_FREQUENCY = 0.4
WEIGHT_DOMAIN = 0.2

# Confidence settings
MIN_CONFIDENCE_FOR_PRELOAD = 0.6
COLD_START_CONFIDENCE = 0.5


def _utcnow_naive() -> datetime:
    """Return naive UTC datetime for compatibility with existing code paths."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class RequestRecord:
    """Single routed request retained for short-horizon tactical forecasting."""

    timestamp: datetime
    domain: TaskDomain
    engine_id: EngineID
    success: bool = True
    latency_ms: float = 0.0

    def age_seconds(self, current_time: Optional[datetime] = None) -> float:
        """Return record age in seconds from the provided or current UTC time."""
        now = current_time or _utcnow_naive()
        return max((now - self.timestamp).total_seconds(), 0.0)


@dataclass
class EngineScore:
    """Per-engine score breakdown used to rank preload order deterministically."""

    engine_id: EngineID
    score_recency: float
    score_frequency: float
    score_domain: float
    score_final: float
    last_used: Optional[datetime]
    use_count_in_window: int
    confidence: float
    reason: str


@dataclass
class PreloadPrediction:
    """Ranked prediction output from deterministic weighted forecasting."""

    predicted_engines: List[EngineID]
    scores: Dict[str, EngineScore]
    domain_hint: Optional[TaskDomain]
    confidence: float
    reasoning: str
    recommendation: str


@dataclass
class PreloadPlan:
    """Executable preload plan with order, urgency partitioning, and estimates."""

    engine_order: List[EngineID]
    always_preload: List[EngineID]
    opportunistic_preload: List[EngineID]
    estimated_time_ms: float
    memory_required_gb: float

    def summary(self) -> str:
        """Return concise string summary suitable for tactical logs."""
        return "\n".join(
            [
                f"Preload order: {[engine.value for engine in self.engine_order]}",
                f"Always preload: {[engine.value for engine in self.always_preload]}",
                f"Opportunistic preload: {[engine.value for engine in self.opportunistic_preload]}",
                f"Estimated time: {self.estimated_time_ms:.0f}ms",
                f"Memory required: {self.memory_required_gb:.1f}GB",
            ]
        )


class PredictivePreloader:
    """
    Predicts which engines should be pre-warmed for upcoming mission traffic.

    Design goals:
      1) Deterministic scoring and ranking for reproducible behavior.
      2) Bounded, recent history (5 minutes or 100 requests).
      3) Explicit/manual preload planning only (no background auto-loading).
    """

    def __init__(
        self,
        registry: Optional[EngineRegistry] = None,
        decay_lambda: float = RECENCY_DECAY_LAMBDA,
    ) -> None:
        self.registry = registry or EngineRegistry()
        self.decay_lambda = float(decay_lambda)
        self.history: "OrderedDict[str, RequestRecord]" = OrderedDict()
        self._history_counter = 0
        self._validate_weights()
        logger.info("PredictivePreloader initialized (deterministic mode)")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def record_request(
        self,
        domain: TaskDomain,
        engine_id: EngineID,
        success: bool = True,
        latency_ms: float = 0.0,
    ) -> None:
        """
        Record a completed request for future tactical preload forecasting.
        """
        now = _utcnow_naive()
        record = RequestRecord(
            timestamp=now,
            domain=domain,
            engine_id=engine_id,
            success=success,
            latency_ms=latency_ms,
        )

        key = f"{self._history_counter:06d}"
        self.history[key] = record
        self._history_counter += 1

        # Keep only short-horizon combat-relevant behavior.
        self._prune_history(now=now)

        logger.debug(
            "Recorded request domain=%s engine=%s success=%s latency_ms=%.2f history=%d",
            domain.value,
            engine_id.value,
            success,
            latency_ms,
            len(self.history),
        )

    def predict_next_engines(
        self,
        domain_hint: Optional[TaskDomain] = None,
        limit: int = 2,
    ) -> PreloadPrediction:
        """
        Predict top engines to warm next.

        Notes:
          - Deterministic ranking is enforced with stable tie-breakers.
          - This method does not trigger any loading side effects.
        """
        now = _utcnow_naive()
        self._prune_history(now=now)
        bounded_limit = self._coerce_limit(limit)
        normalized_hint = self._normalize_domain_hint(domain_hint)

        scores = self._calculate_all_scores(domain_hint=normalized_hint, now=now)
        ranked = self._rank_scores(scores)

        top_pairs = ranked[:bounded_limit]
        predicted_engines = [engine_id for engine_id, _ in top_pairs]
        top_scores = {engine_id.value: score for engine_id, score in top_pairs}

        if not self.history:
            confidence = COLD_START_CONFIDENCE
            reasoning = "Cold start (no recent requests), using domain default"
        else:
            confidence = self._calculate_prediction_confidence(ranked)
            reasoning = self._build_reasoning(ranked_engines=top_pairs, domain_hint=normalized_hint)

        recommendation = self._build_recommendation(predicted=predicted_engines, confidence=confidence)

        prediction = PreloadPrediction(
            predicted_engines=predicted_engines,
            scores=top_scores,
            domain_hint=normalized_hint,
            confidence=confidence,
            reasoning=reasoning,
            recommendation=recommendation,
        )

        logger.info(
            "Prediction engines=%s confidence=%.0f%%",
            [engine.value for engine in predicted_engines],
            confidence * 100.0,
        )
        return prediction

    def build_preload_plan(
        self,
        prediction: PreloadPrediction,
        available_memory_gb: Optional[float] = None,
        always_load_count: int = 1,
    ) -> PreloadPlan:
        """
        Build explicit preload plan from prediction.

        This method only plans and reports; it does not execute loading.
        """
        bounded_always = max(0, int(always_load_count))
        always = prediction.predicted_engines[:bounded_always]
        opportunistic = prediction.predicted_engines[bounded_always:]

        # Adjust opportunistic list to match edge memory budget if provided.
        if available_memory_gb is not None:
            always, opportunistic = self._fit_plan_to_memory_budget(
                always=always,
                opportunistic=opportunistic,
                available_memory_gb=float(available_memory_gb),
            )

        engine_order = always + opportunistic
        estimated_time_ms = self._estimate_preload_time(engine_order)
        memory_required_gb = self._estimate_memory_for_engines(engine_order)

        plan = PreloadPlan(
            engine_order=engine_order,
            always_preload=always,
            opportunistic_preload=opportunistic,
            estimated_time_ms=estimated_time_ms,
            memory_required_gb=memory_required_gb,
        )

        logger.info("Preload plan prepared:\n%s", plan.summary())
        return plan

    def get_history(self, limit: int = 20) -> List[Dict[str, object]]:
        """Return recent history records for observability and tests."""
        bounded = max(0, int(limit))
        records = list(self.history.values())[-bounded:] if bounded > 0 else []
        return [
            {
                "timestamp": record.timestamp.isoformat(),
                "domain": record.domain.value,
                "engine": record.engine_id.value,
                "success": record.success,
                "latency_ms": record.latency_ms,
            }
            for record in records
        ]

    def get_stats(self) -> Dict[str, object]:
        """Return aggregate usage stats over the current bounded history window."""
        if not self.history:
            return {
                "total_requests": 0,
                "history_size": 0,
                "engines_used": [],
                "domains_used": [],
                "most_common_domain": None,
                "most_used_engine": None,
            }

        engines_used = sorted({record.engine_id.value for record in self.history.values()})
        domains_used = sorted({record.domain.value for record in self.history.values()})

        most_used_engine = self._get_most_used_engine()
        most_common_domain = self._get_likely_domain()

        return {
            "total_requests": len(self.history),
            "history_size": len(self.history),
            "engines_used": engines_used,
            "domains_used": domains_used,
            "most_common_domain": most_common_domain.value if most_common_domain else None,
            "most_used_engine": most_used_engine.value if most_used_engine else None,
        }

    def clear_history(self) -> None:
        """Clear preloader history; primarily used by deterministic unit tests."""
        self.history.clear()
        logger.info("Predictive preload history cleared")

    # ---------------------------------------------------------------------
    # Scoring internals
    # ---------------------------------------------------------------------
    def _calculate_all_scores(
        self,
        domain_hint: Optional[TaskDomain],
        now: datetime,
    ) -> Dict[EngineID, EngineScore]:
        target_domain = domain_hint or self._get_likely_domain() or TaskDomain.TACTICAL
        total_requests = len(self.history)
        scores: Dict[EngineID, EngineScore] = {}

        for engine_id in EngineID:
            recency = self._calculate_recency_score(engine_id=engine_id, now=now)
            frequency = self._calculate_frequency_score(engine_id=engine_id, total_requests=total_requests)
            domain = self._calculate_domain_affinity_score(engine_id=engine_id, target_domain=target_domain)
            final_score = self._calculate_final_score(recency=recency, frequency=frequency, domain=domain)
            last_used = self._get_last_used_time(engine_id)
            use_count = self._count_uses_in_window(engine_id=engine_id, now=now)
            confidence = min(max(final_score, 0.0), 1.0)
            reason = (
                f"recency={recency:.2f} frequency={frequency:.2f} "
                f"domain={domain:.2f} final={final_score:.2f}"
            )

            scores[engine_id] = EngineScore(
                engine_id=engine_id,
                score_recency=recency,
                score_frequency=frequency,
                score_domain=domain,
                score_final=final_score,
                last_used=last_used,
                use_count_in_window=use_count,
                confidence=confidence,
                reason=reason,
            )

        return scores

    def _calculate_recency_score(self, engine_id: EngineID, now: datetime) -> float:
        """
        Exponential recency score:
          score = e^(-lambda * seconds_since_last_use)
        """
        last_used = self._get_last_used_time(engine_id=engine_id)
        if last_used is None:
            return 0.0
        age_seconds = max((now - last_used).total_seconds(), 0.0)
        score = math.exp(-self.decay_lambda * age_seconds)
        return min(max(score, 0.0), 1.0)

    def _calculate_frequency_score(self, engine_id: EngineID, total_requests: int) -> float:
        """Frequency score over bounded history window."""
        if total_requests <= 0:
            return 0.0
        use_count = self._count_uses_in_window(engine_id=engine_id, now=_utcnow_naive())
        score = float(use_count) / float(total_requests)
        return min(max(score, 0.0), 1.0)

    def _calculate_domain_affinity_score(self, engine_id: EngineID, target_domain: TaskDomain) -> float:
        """Domain confidence from registry capability priors."""
        score = self.registry.get_capability_score(engine_id, target_domain)
        return min(max(float(score), 0.0), 1.0)

    def _calculate_final_score(self, recency: float, frequency: float, domain: float) -> float:
        """Weighted deterministic score composition."""
        score = (WEIGHT_RECENCY * recency) + (WEIGHT_FREQUENCY * frequency) + (WEIGHT_DOMAIN * domain)
        return min(max(score, 0.0), 1.0)

    def _rank_scores(self, scores: Dict[EngineID, EngineScore]) -> List[Tuple[EngineID, EngineScore]]:
        """
        Deterministically rank scores with explicit tie-breakers.

        Tie-break order:
          1) final score
          2) frequency
          3) recency
          4) domain
          5) lexical engine id
        """
        return sorted(
            scores.items(),
            key=lambda item: (
                -item[1].score_final,
                -item[1].score_frequency,
                -item[1].score_recency,
                -item[1].score_domain,
                item[0].value,
            ),
        )

    def _calculate_prediction_confidence(self, ranked: List[Tuple[EngineID, EngineScore]]) -> float:
        """
        Calculate ensemble confidence from top-ranked score and separation margin.

        The confidence remains deterministic and bounded to [0, 1].
        """
        if not ranked:
            return COLD_START_CONFIDENCE
        top_score = ranked[0][1].score_final
        if len(ranked) == 1:
            return min(max(top_score, 0.0), 1.0)
        second_score = ranked[1][1].score_final
        margin = max(top_score - second_score, 0.0)
        # Tactical rationale: margin rewards clear winner without discarding base strength.
        confidence = min(max((0.85 * top_score) + (0.15 * margin), 0.0), 1.0)
        return confidence

    # ---------------------------------------------------------------------
    # Plan/reasoning internals
    # ---------------------------------------------------------------------
    def _build_reasoning(
        self,
        ranked_engines: List[Tuple[EngineID, EngineScore]],
        domain_hint: Optional[TaskDomain],
    ) -> str:
        """Build concise, operator-friendly reason string."""
        if not ranked_engines:
            return "No ranked engines available"

        top_engine, top_score = ranked_engines[0]
        parts = [
            f"{top_engine.value} likely",
            f"confidence {top_score.confidence:.0%}",
            f"{top_score.use_count_in_window} recent uses",
        ]
        if domain_hint is not None:
            parts.append(f"domain hint={domain_hint.value}")
        return ", ".join(parts)

    def _build_recommendation(self, predicted: List[EngineID], confidence: float) -> str:
        """Build explicit action recommendation without triggering side effects."""
        if not predicted:
            return "No recommendation (empty prediction set)"
        if confidence < MIN_CONFIDENCE_FOR_PRELOAD:
            return f"Confidence low ({confidence:.0%}), defer preload"
        if len(predicted) == 1:
            return f"Preload {predicted[0].value}"
        opportunistic_names = ", ".join(engine.value for engine in predicted[1:])
        return f"Preload {predicted[0].value}, opportunistic {opportunistic_names}"

    def _fit_plan_to_memory_budget(
        self,
        always: List[EngineID],
        opportunistic: List[EngineID],
        available_memory_gb: float,
    ) -> Tuple[List[EngineID], List[EngineID]]:
        """
        Shrink opportunistic list until plan fits memory budget.

        Tactical rationale: never drop always-preload candidates automatically;
        those represent highest-priority likely engines.
        """
        always_copy = list(always)
        opportunistic_copy = list(opportunistic)

        if available_memory_gb <= 0.0:
            logger.warning("Non-positive memory budget %.2fGB, dropping opportunistic preloads", available_memory_gb)
            return always_copy, []

        while opportunistic_copy:
            total_memory = self._estimate_memory_for_engines(always_copy + opportunistic_copy)
            if total_memory <= available_memory_gb:
                break
            dropped = opportunistic_copy.pop()
            logger.info(
                "Dropping opportunistic preload %s to fit %.2fGB budget",
                dropped.value,
                available_memory_gb,
            )

        always_memory = self._estimate_memory_for_engines(always_copy)
        if always_memory > available_memory_gb:
            logger.warning(
                "Always preload set requires %.2fGB > %.2fGB budget; retaining always set for caller decision",
                always_memory,
                available_memory_gb,
            )

        return always_copy, opportunistic_copy

    def _estimate_preload_time(self, engines: List[EngineID]) -> float:
        """Estimate sequential warm time from per-engine baseline latencies."""
        total_ms = 0.0
        for engine_id in engines:
            config = self.registry.get_config(engine_id)
            # Tactical overhead models disk I/O and allocator warmup in edge boots.
            total_ms += float(config.inference_latency_ms) * 1.5
        return total_ms

    def _estimate_memory_for_engines(self, engines: List[EngineID]) -> float:
        """Estimate total memory required to co-resident warm selected engines."""
        if not engines:
            return 0.0
        return float(self.registry.get_total_memory_required(engines))

    # ---------------------------------------------------------------------
    # History/window internals
    # ---------------------------------------------------------------------
    def _prune_history(self, now: datetime) -> None:
        """
        Prune history to the rolling tactical window:
          - remove records older than RECENCY_WINDOW_SECONDS
          - cap to MAX_HISTORY_SIZE most recent records
        """
        cutoff = now - timedelta(seconds=RECENCY_WINDOW_SECONDS)

        while self.history:
            first_key = next(iter(self.history))
            first_record = self.history[first_key]
            if first_record.timestamp >= cutoff:
                break
            self.history.popitem(last=False)

        while len(self.history) > MAX_HISTORY_SIZE:
            self.history.popitem(last=False)

    def _iter_window_records(self, now: datetime) -> Iterable[RequestRecord]:
        """Yield records still inside the active recency window."""
        cutoff = now - timedelta(seconds=RECENCY_WINDOW_SECONDS)
        for record in self.history.values():
            if record.timestamp >= cutoff:
                yield record

    def _count_uses_in_window(self, engine_id: EngineID, now: datetime) -> int:
        """Count uses for a specific engine within the active rolling window."""
        return sum(1 for record in self._iter_window_records(now=now) if record.engine_id == engine_id)

    def _get_last_used_time(self, engine_id: EngineID) -> Optional[datetime]:
        """Return timestamp of most recent use for the given engine."""
        for record in reversed(self.history.values()):
            if record.engine_id == engine_id:
                return record.timestamp
        return None

    def _get_likely_domain(self) -> Optional[TaskDomain]:
        """Infer most common domain in current bounded history window."""
        if not self.history:
            return None
        counts: Dict[TaskDomain, int] = {}
        for record in self.history.values():
            counts[record.domain] = counts.get(record.domain, 0) + 1
        return max(counts.items(), key=lambda item: item[1])[0]

    def _get_most_used_engine(self) -> Optional[EngineID]:
        """Return most frequently used engine in bounded history window."""
        if not self.history:
            return None
        counts: Dict[EngineID, int] = {}
        for record in self.history.values():
            counts[record.engine_id] = counts.get(record.engine_id, 0) + 1
        return max(counts.items(), key=lambda item: item[1])[0]

    # ---------------------------------------------------------------------
    # Validation and normalization internals
    # ---------------------------------------------------------------------
    def _validate_weights(self) -> None:
        """Guard against accidental non-normalized scoring constants."""
        total = WEIGHT_RECENCY + WEIGHT_FREQUENCY + WEIGHT_DOMAIN
        if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")

    def _normalize_domain_hint(self, domain_hint: Optional[TaskDomain]) -> Optional[TaskDomain]:
        """Normalize optional domain hint; keeps type-safe deterministic behavior."""
        if domain_hint is None:
            return None
        if isinstance(domain_hint, TaskDomain):
            return domain_hint
        raise TypeError("domain_hint must be TaskDomain or None")

    def _coerce_limit(self, limit: int) -> int:
        """Normalize prediction limit to safe deterministic bounds."""
        max_engines = len(list(EngineID))
        bounded = int(limit)
        if bounded < 1:
            return 1
        if bounded > max_engines:
            return max_engines
        return bounded

