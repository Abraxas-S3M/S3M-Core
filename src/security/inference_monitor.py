"""Runtime inference anomaly monitoring for tactical AI/ML operations.

This module detects behavioral anomalies in model inference calls during
mission-time execution, complementing static model integrity checks.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

try:  # Optional compatibility soft-import for Chunk 5 model trust types.
    from src.security.model_trust import ModelDomain as _Chunk5ModelDomain  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover
    _Chunk5ModelDomain = None  # type: ignore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class DetectionType(str, Enum):
    CONFIDENCE_ANOMALY = "CONFIDENCE_ANOMALY"
    LATENCY_ANOMALY = "LATENCY_ANOMALY"
    OUTPUT_DEVIATION = "OUTPUT_DEVIATION"
    DISTRIBUTION_DRIFT = "DISTRIBUTION_DRIFT"
    INCONSISTENT_REASONING = "INCONSISTENT_REASONING"
    COMBINED = "COMBINED"


class AlertSeverity(str, Enum):
    NEGLIGIBLE = "NEGLIGIBLE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ModelDomain(str, Enum):
    TACTICAL = "TACTICAL"
    REASONING = "REASONING"
    PLANNING = "PLANNING"
    ARABIC_NLP = "ARABIC_NLP"
    MULTI = "MULTI"
    UNKNOWN = "UNKNOWN"


class InferenceObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    model_id: str
    model_name: str
    domain: ModelDomain = ModelDomain.UNKNOWN
    prompt_hash: Optional[str] = None
    response_length: int = Field(ge=0)
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    latency_ms: float = Field(ge=0)
    reasoning_steps: int = Field(default=0, ge=0)
    token_distribution: Dict[str, float] = Field(default_factory=dict)
    belief_state_id: Optional[str] = None
    call_context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)

    @field_validator("model_name")
    @classmethod
    def _validate_model_name(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("model_name must not be blank")
        return value

    @field_validator("token_distribution")
    @classmethod
    def _validate_token_distribution(cls, value: Dict[str, float]) -> Dict[str, float]:
        total = 0.0
        for token, prob in value.items():
            if prob < 0:
                raise ValueError(f"token_distribution[{token}] must be non-negative")
            total += prob
        if total > 1.001:
            raise ValueError("token_distribution values sum must be <= 1.001")
        return value


class EWMABaseline(BaseModel):
    model_id: str
    n_observations: int = Field(default=0, ge=0)

    mean_confidence: float = 0.5
    var_confidence: float = Field(default=0.04, ge=0)

    mean_latency_ms: float = Field(default=100.0, ge=0)
    var_latency_ms: float = Field(default=100.0, ge=0)

    mean_response_length: float = Field(default=200.0, ge=0)
    var_response_length: float = Field(default=400.0, ge=0)

    mean_reasoning_steps: float = Field(default=0.0, ge=0)
    var_reasoning_steps: float = Field(default=1.0, ge=0)

    token_dist_baseline: Dict[str, float] = Field(default_factory=dict)

    last_updated: datetime = Field(default_factory=_utcnow)
    alpha: float = Field(default=0.1, gt=0, le=1)

    def std_confidence(self) -> float:
        return max(1e-6, math.sqrt(self.var_confidence))

    def std_latency_ms(self) -> float:
        return max(1e-6, math.sqrt(self.var_latency_ms))

    def std_response_length(self) -> float:
        return max(1e-6, math.sqrt(self.var_response_length))

    def std_reasoning_steps(self) -> float:
        return max(1e-6, math.sqrt(self.var_reasoning_steps))

    def is_warm(self, min_obs: int) -> bool:
        return self.n_observations >= min_obs

    def update(self, obs: InferenceObservation) -> None:
        alpha = self.alpha
        one_minus = 1.0 - alpha

        if obs.confidence_score is not None:
            new_mean_conf = alpha * float(obs.confidence_score) + one_minus * self.mean_confidence
            self.var_confidence = alpha * (float(obs.confidence_score) - new_mean_conf) ** 2 + one_minus * self.var_confidence
            self.mean_confidence = new_mean_conf

        new_mean_latency = alpha * float(obs.latency_ms) + one_minus * self.mean_latency_ms
        self.var_latency_ms = alpha * (float(obs.latency_ms) - new_mean_latency) ** 2 + one_minus * self.var_latency_ms
        self.mean_latency_ms = new_mean_latency

        new_mean_len = alpha * float(obs.response_length) + one_minus * self.mean_response_length
        self.var_response_length = alpha * (float(obs.response_length) - new_mean_len) ** 2 + one_minus * self.var_response_length
        self.mean_response_length = new_mean_len

        steps_value = float(obs.reasoning_steps)
        new_mean_steps = alpha * steps_value + one_minus * self.mean_reasoning_steps
        self.var_reasoning_steps = alpha * (steps_value - new_mean_steps) ** 2 + one_minus * self.var_reasoning_steps
        self.mean_reasoning_steps = new_mean_steps

        all_tokens = set(self.token_dist_baseline.keys()) | set(obs.token_distribution.keys())
        for token in all_tokens:
            old_p = self.token_dist_baseline.get(token, 0.0)
            new_p = obs.token_distribution.get(token, 0.0)
            blended = alpha * new_p + one_minus * old_p
            if blended < 1e-6:
                self.token_dist_baseline.pop(token, None)
            else:
                self.token_dist_baseline[token] = blended

        self.n_observations += 1
        self.last_updated = _utcnow()


class DetectorResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    detection_type: DetectionType
    triggered: bool
    sub_score: float = Field(ge=0, le=1)
    z_score: Optional[float] = None
    measured_value: Optional[float] = None
    baseline_value: Optional[float] = None
    threshold: Optional[float] = None
    detail: str
    detail_ar: Optional[str] = None


class AnomalyScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    composite: float = Field(ge=0, le=1)
    sub_scores: Dict[str, float]
    weights_used: Dict[str, float]
    severity: AlertSeverity

    def is_anomalous(self, threshold: float = 0.20) -> bool:
        return self.composite >= threshold


class AnomalyAlert(BaseModel):
    model_config = ConfigDict(frozen=True)

    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    model_id: str
    model_name: str
    domain: ModelDomain
    detection_types: List[DetectionType]
    anomaly_score: AnomalyScore
    detector_results: List[DetectorResult]
    observation_id: str
    baseline_n_obs: int
    rationale: str
    rationale_ar: str
    recommended_action: str
    recommended_action_ar: str
    belief_state_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)

    def is_critical(self) -> bool:
        return self.anomaly_score.severity == AlertSeverity.CRITICAL

    def requires_human_review(self) -> bool:
        return self.anomaly_score.severity in {AlertSeverity.HIGH, AlertSeverity.CRITICAL}


class MonitorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    confidence_z_threshold: float = Field(default=3.0, gt=0)
    latency_z_threshold: float = Field(default=4.0, gt=0)
    deviation_z_threshold: float = Field(default=3.5, gt=0)
    drift_js_threshold: float = Field(default=0.25, gt=0, le=1)
    consistency_ratio_threshold: float = Field(default=0.40, gt=0, le=1)
    alert_threshold: float = Field(default=0.20, ge=0, le=1)
    min_baseline_observations: int = Field(default=10, ge=1)
    ewma_alpha: float = Field(default=0.1, gt=0, le=1)
    max_window_per_model: int = Field(default=200, ge=1)
    detector_weights: Dict[str, float] = Field(default_factory=dict)

    @field_validator("detector_weights")
    @classmethod
    def _validate_detector_weights(cls, value: Dict[str, float]) -> Dict[str, float]:
        if not value:
            return value
        expected = {
            DetectionType.CONFIDENCE_ANOMALY.value,
            DetectionType.LATENCY_ANOMALY.value,
            DetectionType.OUTPUT_DEVIATION.value,
            DetectionType.DISTRIBUTION_DRIFT.value,
            DetectionType.INCONSISTENT_REASONING.value,
        }
        if set(value.keys()) != expected:
            raise ValueError("detector_weights must include exactly the five detector keys")
        total = sum(value.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError("detector_weights must sum to 1.0 (+/- 0.001)")
        if any(weight < 0 for weight in value.values()):
            raise ValueError("detector_weights must be non-negative")
        return value

    @classmethod
    def default(cls) -> "MonitorConfig":
        return cls()

    @classmethod
    def sensitive(cls) -> "MonitorConfig":
        return cls(
            confidence_z_threshold=2.0,
            drift_js_threshold=0.15,
            alert_threshold=0.15,
        )

    @classmethod
    def permissive(cls) -> "MonitorConfig":
        return cls(
            confidence_z_threshold=4.0,
            drift_js_threshold=0.40,
            alert_threshold=0.30,
            min_baseline_observations=20,
        )


def _kl(p: Dict[str, float], q: Dict[str, float], eps: float = 1e-10) -> float:
    total = 0.0
    keys = set(p.keys()) | set(q.keys())
    for key in keys:
        p_val = max(eps, p.get(key, 0.0))
        q_val = max(eps, q.get(key, 0.0))
        total += p_val * math.log2(p_val / q_val)
    return max(0.0, total)


def _js_divergence(p: Dict[str, float], q: Dict[str, float], eps: float = 1e-10) -> float:
    keys = set(p.keys()) | set(q.keys())
    if not keys:
        return 0.0

    p_smooth = {k: max(eps, p.get(k, 0.0)) for k in keys}
    q_smooth = {k: max(eps, q.get(k, 0.0)) for k in keys}

    p_sum = sum(p_smooth.values())
    q_sum = sum(q_smooth.values())
    if p_sum <= 0 or q_sum <= 0:
        return 0.0

    p_norm = {k: v / p_sum for k, v in p_smooth.items()}
    q_norm = {k: v / q_sum for k, v in q_smooth.items()}
    m = {k: 0.5 * (p_norm[k] + q_norm[k]) for k in keys}

    js = 0.5 * _kl(p_norm, m, eps=eps) + 0.5 * _kl(q_norm, m, eps=eps)
    return _clamp(js, 0.0, 1.0)


def detect_confidence_anomaly(obs: InferenceObservation, baseline: EWMABaseline, threshold: float) -> DetectorResult:
    if obs.confidence_score is None:
        return DetectorResult(
            detection_type=DetectionType.CONFIDENCE_ANOMALY,
            triggered=False,
            sub_score=0.0,
            detail="Confidence unavailable; detector skipped.",
            detail_ar="لا توجد قيمة ثقة؛ تم تجاوز فاحص الثقة.",
        )

    z = (float(obs.confidence_score) - baseline.mean_confidence) / baseline.std_confidence()
    abs_z = abs(z)
    triggered = abs_z > threshold
    sub_score = _clamp(abs_z / (threshold * 2.0), 0.0, 1.0)
    detail = (
        f"Confidence z-score={z:.4f}, measured={obs.confidence_score:.4f}, "
        f"baseline={baseline.mean_confidence:.4f}, threshold={threshold:.4f}"
    )
    detail_ar = (
        f"قيمة Z للثقة={z:.4f}، القيمة المرصودة={obs.confidence_score:.4f}، "
        f"خط الأساس={baseline.mean_confidence:.4f}، العتبة={threshold:.4f}"
    )
    return DetectorResult(
        detection_type=DetectionType.CONFIDENCE_ANOMALY,
        triggered=triggered,
        sub_score=sub_score,
        z_score=z,
        measured_value=float(obs.confidence_score),
        baseline_value=baseline.mean_confidence,
        threshold=threshold,
        detail=detail,
        detail_ar=detail_ar,
    )


def detect_latency_anomaly(obs: InferenceObservation, baseline: EWMABaseline, threshold: float) -> DetectorResult:
    z = (float(obs.latency_ms) - baseline.mean_latency_ms) / baseline.std_latency_ms()
    triggered = z > threshold
    sub_score = _clamp(z / (threshold * 2.0), 0.0, 1.0)
    detail = (
        f"Latency z-score={z:.4f}, measured={obs.latency_ms:.4f}ms, "
        f"baseline={baseline.mean_latency_ms:.4f}ms, threshold={threshold:.4f}"
    )
    detail_ar = (
        f"قيمة Z للزمن={z:.4f}، الزمن المرصود={obs.latency_ms:.4f} مللي ثانية، "
        f"خط الأساس={baseline.mean_latency_ms:.4f} مللي ثانية، العتبة={threshold:.4f}"
    )
    return DetectorResult(
        detection_type=DetectionType.LATENCY_ANOMALY,
        triggered=triggered,
        sub_score=sub_score,
        z_score=z,
        measured_value=float(obs.latency_ms),
        baseline_value=baseline.mean_latency_ms,
        threshold=threshold,
        detail=detail,
        detail_ar=detail_ar,
    )


def detect_output_deviation(obs: InferenceObservation, baseline: EWMABaseline, threshold: float) -> DetectorResult:
    z_len = abs((float(obs.response_length) - baseline.mean_response_length) / baseline.std_response_length())
    z_steps = abs((float(obs.reasoning_steps) - baseline.mean_reasoning_steps) / baseline.std_reasoning_steps())
    z_max = max(z_len, z_steps)
    triggered = z_max > threshold
    sub_score = _clamp(z_max / (threshold * 2.0), 0.0, 1.0)
    detail = (
        f"Output deviation z_len={z_len:.4f}, z_steps={z_steps:.4f}, z_max={z_max:.4f}, "
        f"threshold={threshold:.4f}"
    )
    detail_ar = (
        f"انحراف المخرجات: Z للطول={z_len:.4f}، Z لخطوات الاستدلال={z_steps:.4f}، "
        f"الأقصى={z_max:.4f}، العتبة={threshold:.4f}"
    )
    return DetectorResult(
        detection_type=DetectionType.OUTPUT_DEVIATION,
        triggered=triggered,
        sub_score=sub_score,
        z_score=z_max,
        measured_value=z_max,
        baseline_value=0.0,
        threshold=threshold,
        detail=detail,
        detail_ar=detail_ar,
    )


def detect_distribution_drift(obs: InferenceObservation, baseline: EWMABaseline, threshold: float) -> DetectorResult:
    if not obs.token_distribution or not baseline.token_dist_baseline:
        return DetectorResult(
            detection_type=DetectionType.DISTRIBUTION_DRIFT,
            triggered=False,
            sub_score=0.0,
            detail="No token distribution available.",
            detail_ar="لا يوجد توزيع رموز متاح.",
        )

    js_div = _js_divergence(obs.token_distribution, baseline.token_dist_baseline, eps=1e-10)
    triggered = js_div > threshold
    sub_score = _clamp(js_div / max(threshold * 2.0, 1e-6), 0.0, 1.0)
    detail = f"Distribution drift JS divergence={js_div:.6f}, threshold={threshold:.4f}"
    detail_ar = f"انجراف التوزيع: تباعد JS={js_div:.6f}، العتبة={threshold:.4f}"
    return DetectorResult(
        detection_type=DetectionType.DISTRIBUTION_DRIFT,
        triggered=triggered,
        sub_score=sub_score,
        measured_value=js_div,
        threshold=threshold,
        detail=detail,
        detail_ar=detail_ar,
    )


def detect_reasoning_inconsistency(
    obs: InferenceObservation,
    baseline: EWMABaseline,
    consistency_threshold: float,
) -> DetectorResult:
    if baseline.mean_reasoning_steps < 0.5:
        return DetectorResult(
            detection_type=DetectionType.INCONSISTENT_REASONING,
            triggered=False,
            sub_score=0.0,
            detail="Model does not emit reasoning steps.",
            detail_ar="النموذج لا يصدر خطوات استدلال.",
        )

    ratio = float(obs.reasoning_steps) / max(1.0, baseline.mean_reasoning_steps)
    triggered = ratio < consistency_threshold
    if triggered:
        sub_score = _clamp(1.0 - (ratio / consistency_threshold), 0.0, 1.0)
    else:
        sub_score = 0.0
    measured_steps = float(obs.reasoning_steps)
    detail = (
        f"Reasoning consistency ratio={ratio:.4f}, measured_steps={measured_steps:.4f}, "
        f"baseline_steps={baseline.mean_reasoning_steps:.4f}, threshold={consistency_threshold:.4f}"
    )
    detail_ar = (
        f"اتساق الاستدلال: النسبة={ratio:.4f}، الخطوات المرصودة={float(obs.reasoning_steps):.4f}، "
        f"خط الأساس={baseline.mean_reasoning_steps:.4f}، العتبة={consistency_threshold:.4f}"
    )
    return DetectorResult(
        detection_type=DetectionType.INCONSISTENT_REASONING,
        triggered=triggered,
        sub_score=sub_score,
        measured_value=ratio,
        baseline_value=baseline.mean_reasoning_steps,
        threshold=consistency_threshold,
        detail=detail,
        detail_ar=detail_ar,
    )


class InferenceMonitor:
    def __init__(self, config: Optional[MonitorConfig] = None) -> None:
        self.config = config or MonitorConfig()
        self._lock = threading.RLock()
        self._baselines: Dict[str, EWMABaseline] = {}
        self._windows: Dict[str, List[InferenceObservation]] = {}
        self._alert_log: List[AnomalyAlert] = []
        self._obs_log: List[InferenceObservation] = []

    def observe(self, obs: InferenceObservation) -> Optional[AnomalyAlert]:
        """Process one inference observation and return an alert when anomalous."""
        with self._lock:
            baseline = self._baselines.get(obs.model_id)
            if baseline is None:
                baseline = EWMABaseline(model_id=obs.model_id, alpha=self.config.ewma_alpha)
                self._baselines[obs.model_id] = baseline

            if not baseline.is_warm(self.config.min_baseline_observations):
                baseline.update(obs)
                self._append_to_window(obs)
                self._obs_log.append(obs)
                return None

            results = [
                detect_confidence_anomaly(obs, baseline, self.config.confidence_z_threshold),
                detect_latency_anomaly(obs, baseline, self.config.latency_z_threshold),
                detect_output_deviation(obs, baseline, self.config.deviation_z_threshold),
                detect_distribution_drift(obs, baseline, self.config.drift_js_threshold),
                detect_reasoning_inconsistency(obs, baseline, self.config.consistency_ratio_threshold),
            ]

            weights = self.config.detector_weights or self._default_weights()
            composite = sum(weights.get(r.detection_type.value, 0.0) * r.sub_score for r in results)
            composite = _clamp(composite, 0.0, 1.0)
            severity = self._score_to_severity(composite)
            sub_scores = {r.detection_type.value: r.sub_score for r in results}
            score = AnomalyScore(
                composite=composite,
                sub_scores=sub_scores,
                weights_used=weights,
                severity=severity,
            )

            baseline.update(obs)
            self._append_to_window(obs)
            self._obs_log.append(obs)

            if composite < self.config.alert_threshold:
                return None

            triggered_types = [r.detection_type for r in results if r.triggered]
            if len(triggered_types) > 1 and any(t != DetectionType.COMBINED for t in triggered_types):
                triggered_types.append(DetectionType.COMBINED)

            alert = AnomalyAlert(
                model_id=obs.model_id,
                model_name=obs.model_name,
                domain=obs.domain,
                detection_types=triggered_types,
                anomaly_score=score,
                detector_results=results,
                observation_id=obs.observation_id,
                baseline_n_obs=baseline.n_observations,
                rationale=self._build_rationale_en(results, score, obs),
                rationale_ar=self._build_rationale_ar(results, score, obs),
                recommended_action=self._recommended_action_en(score.severity, triggered_types),
                recommended_action_ar=self._recommended_action_ar(score.severity, triggered_types),
                belief_state_id=obs.belief_state_id,
            )
            self._alert_log.append(alert)
            return alert

    def observe_batch(self, observations: List[InferenceObservation]) -> List[AnomalyAlert]:
        """Process a batch of observations and return produced anomaly alerts."""
        alerts: List[AnomalyAlert] = []
        for obs in observations:
            alert = self.observe(obs)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def get_baseline(self, model_id: str) -> Optional[EWMABaseline]:
        """Return the current EWMA baseline for a model, if available."""
        with self._lock:
            return self._baselines.get(model_id)

    def alert_log(self, n: int = 50) -> List[AnomalyAlert]:
        """Return up to the last n alerts in chronological order."""
        with self._lock:
            return list(self._alert_log[-n:])

    def observation_log(self, model_id: Optional[str] = None, n: int = 100) -> List[InferenceObservation]:
        """Return up to the last n observations, optionally filtered by model_id."""
        with self._lock:
            if model_id is None:
                return list(self._obs_log[-n:])
            filtered = [obs for obs in self._obs_log if obs.model_id == model_id]
            return filtered[-n:]

    def reset_baseline(self, model_id: str) -> None:
        """Clear a model baseline and rolling window to force re-baselining."""
        with self._lock:
            self._baselines.pop(model_id, None)
            self._windows.pop(model_id, None)

    def summary(self, model_id: str) -> Dict[str, Any]:
        """Return monitoring summary metrics for one model."""
        with self._lock:
            baseline = self._baselines.get(model_id)
            model_alerts = [a for a in self._alert_log if a.model_id == model_id]
            last_alert_severity = model_alerts[-1].anomaly_score.severity.value if model_alerts else None
            return {
                "model_id": model_id,
                "n_observations": baseline.n_observations if baseline else 0,
                "n_alerts": len(model_alerts),
                "baseline_warm": baseline.is_warm(self.config.min_baseline_observations) if baseline else False,
                "mean_confidence": baseline.mean_confidence if baseline else None,
                "mean_latency_ms": baseline.mean_latency_ms if baseline else None,
                "mean_response_length": baseline.mean_response_length if baseline else None,
                "last_alert_severity": last_alert_severity,
                "last_updated": baseline.last_updated if baseline else None,
            }

    def _append_to_window(self, obs: InferenceObservation) -> None:
        window = self._windows.setdefault(obs.model_id, [])
        window.append(obs)
        if len(window) > self.config.max_window_per_model:
            del window[: len(window) - self.config.max_window_per_model]

    @staticmethod
    def _score_to_severity(score: float) -> AlertSeverity:
        if score < 0.20:
            return AlertSeverity.NEGLIGIBLE
        if score < 0.40:
            return AlertSeverity.LOW
        if score < 0.60:
            return AlertSeverity.MEDIUM
        if score < 0.80:
            return AlertSeverity.HIGH
        return AlertSeverity.CRITICAL

    @staticmethod
    def _default_weights() -> Dict[str, float]:
        return {
            DetectionType.CONFIDENCE_ANOMALY.value: 0.30,
            DetectionType.LATENCY_ANOMALY.value: 0.15,
            DetectionType.OUTPUT_DEVIATION.value: 0.20,
            DetectionType.DISTRIBUTION_DRIFT.value: 0.25,
            DetectionType.INCONSISTENT_REASONING.value: 0.10,
        }

    def _build_rationale_en(
        self,
        results: List[DetectorResult],
        score: AnomalyScore,
        obs: InferenceObservation,
    ) -> str:
        triggered = [r for r in results if r.triggered]
        if triggered:
            trigger_text = ", ".join(f"{r.detection_type.value}:{r.sub_score:.3f}" for r in triggered)
        else:
            trigger_text = "None"
        n_obs = self._baselines.get(obs.model_id).n_observations if obs.model_id in self._baselines else 0
        return (
            f"Model={obs.model_name}, domain={obs.domain.value}, composite={score.composite:.4f}, "
            f"severity={score.severity.value}, triggered={trigger_text}, baseline_observations={n_obs}"
        )

    def _build_rationale_ar(
        self,
        results: List[DetectorResult],
        score: AnomalyScore,
        obs: InferenceObservation,
    ) -> str:
        triggered = [r for r in results if r.triggered]
        if triggered:
            trigger_text = "، ".join(f"{r.detection_type.value}:{r.sub_score:.3f}" for r in triggered)
        else:
            trigger_text = "لا يوجد"
        n_obs = self._baselines.get(obs.model_id).n_observations if obs.model_id in self._baselines else 0
        return (
            f"النموذج={obs.model_name}، المجال={obs.domain.value}، الدرجة المركبة={score.composite:.4f}، "
            f"الشدة={score.severity.value}، المؤشرات المفعلة={trigger_text}، عدد ملاحظات خط الأساس={n_obs}"
        )

    @staticmethod
    def _recommended_action_en(severity: AlertSeverity, triggered_types: List[DetectionType]) -> str:
        _ = triggered_types
        if severity == AlertSeverity.CRITICAL:
            return "Immediately suspend model and trigger human review. Quarantine inference outputs."
        if severity == AlertSeverity.HIGH:
            return "Flag outputs for manual review. Check model trust state via ModelTrustRegistry."
        if severity == AlertSeverity.MEDIUM:
            return "Monitor closely. Consider re-attestation if pattern persists."
        return "Continue monitoring. No immediate action required."

    @staticmethod
    def _recommended_action_ar(severity: AlertSeverity, triggered_types: List[DetectionType]) -> str:
        _ = triggered_types
        if severity == AlertSeverity.CRITICAL:
            return "أوقف النموذج فوراً وفعّل المراجعة البشرية. اعزل مخرجات الاستدلال."
        if severity == AlertSeverity.HIGH:
            return "علّم المخرجات للمراجعة اليدوية وتحقق من حالة الثقة عبر سجل الثقة."
        if severity == AlertSeverity.MEDIUM:
            return "راقب عن كثب وفكّر في إعادة التحقق إذا استمر النمط."
        return "استمر في المراقبة ولا يلزم إجراء فوري."

    @staticmethod
    def _js_divergence(p: Dict[str, float], q: Dict[str, float], eps: float = 1e-10) -> float:
        return _js_divergence(p, q, eps=eps)

    @staticmethod
    def _kl(p: Dict[str, float], q: Dict[str, float], eps: float = 1e-10) -> float:
        return _kl(p, q, eps=eps)


def build_belief_update_from_alert(alert: AnomalyAlert, hypothesis_ids: List[str]) -> Dict[str, Any]:
    """Build a Chunk 1-compatible BeliefUpdate payload from an anomaly alert."""
    composite = _clamp(alert.anomaly_score.composite, 0.0, 1.0)
    delta_value = -composite * 0.1
    return {
        "source": "SECURITY_RUNTIME",
        "delta": {hid: delta_value for hid in hypothesis_ids},
        "confidence_shift": _clamp(-composite * 0.2, -1.0, 1.0),
        "justification": alert.rationale,
        "justification_ar": alert.rationale_ar,
    }


__all__ = [
    "AlertSeverity",
    "AnomalyAlert",
    "AnomalyScore",
    "DetectionType",
    "DetectorResult",
    "EWMABaseline",
    "InferenceMonitor",
    "InferenceObservation",
    "ModelDomain",
    "MonitorConfig",
    "build_belief_update_from_alert",
    "detect_confidence_anomaly",
    "detect_distribution_drift",
    "detect_latency_anomaly",
    "detect_output_deviation",
    "detect_reasoning_inconsistency",
]
