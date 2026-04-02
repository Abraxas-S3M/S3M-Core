"""Operational Picture Service — runtime integration of all S3M subsystems.

Wires six intelligence layers into one coherent flow:
  1) Ingest fused entity snapshots
  2) Correlate observations to threat genomes
  3) Run short-horizon forecasts
  4) Apply doctrine-driven confidence policies
  5) Feed forecasts into a live mirror for validation
  6) Compose a unified OperationalPicture

This module is a thin coordinator: each capability remains isolated and
testable. The service degrades gracefully when optional subsystems are not
available in a given deployment.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- Prediction (present in this repository) ---
from src.prediction.prediction_models import EntitySnapshot, ForecastBundle, PredictionRequest
from src.prediction.short_horizon_predictor import ShortHorizonPredictor

# Optional prediction helpers (present in some S3M variants).
try:  # pragma: no cover - exercised only when optional module exists
    from src.prediction.pattern_memory import PatternMemory  # type: ignore
except Exception:  # pragma: no cover - fallback path is test-covered
    class PatternMemory:  # type: ignore[override]
        """Fallback tactical pattern memory used when extension module is absent."""

        def register_defaults(self) -> None:
            """Register built-in behavioral templates (no-op fallback)."""


try:  # pragma: no cover - exercised only when optional module exists
    from src.prediction.confidence_calibrator import ConfidenceCalibrator  # type: ignore
except Exception:  # pragma: no cover - fallback path is test-covered
    class ConfidenceCalibrator:  # type: ignore[override]
        """Fallback confidence calibrator that enforces bounded scores."""

        @staticmethod
        def calibrate(score: float) -> float:
            return max(0.0, min(1.0, float(score)))


# --- Threat genome core (present in this repository) ---
from src.threat_genome.models import ThreatGenome
from src.threat_genome.genome_store import ThreatGenomeStore


# =====================================================================
# Fallback Doctrine Layer (used when doctrine package is absent)
# =====================================================================


@dataclass
class _EnumLike:
    """Small enum-like wrapper used to mirror expected `.value` accesses."""

    value: str


@dataclass
class _DoctrineConfidenceConfig:
    alert_confidence_threshold: float = 0.55
    conservative_factor: float = 1.15


@dataclass
class _DoctrineEngagementConfig:
    escalation_tolerance: _EnumLike = field(default_factory=lambda: _EnumLike("conservative"))


@dataclass
class _DoctrineReportingConfig:
    detail_level: _EnumLike = field(default_factory=lambda: _EnumLike("high"))


@dataclass
class DoctrineProfile:
    """Doctrine profile controls risk posture for operator-facing confidence."""

    name: str
    confidence: _DoctrineConfidenceConfig = field(default_factory=_DoctrineConfidenceConfig)
    engagement: _DoctrineEngagementConfig = field(default_factory=_DoctrineEngagementConfig)
    reporting: _DoctrineReportingConfig = field(default_factory=_DoctrineReportingConfig)


@dataclass
class _BiasAdjustment:
    """One doctrinal adjustment applied to an evidence score."""

    kind: str
    detail: str
    delta: float

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "delta": round(self.delta, 4)}


@dataclass
class BiasResult:
    """Result of applying doctrine policy to a raw confidence value."""

    raw_value: float
    adjusted_value: float
    adjustments: List[_BiasAdjustment] = field(default_factory=list)


@dataclass
class FormattedReport:
    """Structured explanation for doctrine application (kept for compatibility)."""

    lines: List[str] = field(default_factory=list)


class DoctrineProfileManager:
    """Minimal doctrine registry with an active profile selector."""

    def __init__(self) -> None:
        self._profiles: Dict[str, DoctrineProfile] = {}
        self._active_name: Optional[str] = None

    def register_builtin_profiles(self) -> None:
        # Saudi/GCC defensive baseline tuned for cautious escalation decisions.
        self._profiles["saudi_gulf_defensive"] = DoctrineProfile(
            name="saudi_gulf_defensive",
            confidence=_DoctrineConfidenceConfig(
                alert_confidence_threshold=0.55,
                conservative_factor=1.15,
            ),
            engagement=_DoctrineEngagementConfig(
                escalation_tolerance=_EnumLike("conservative_strict"),
            ),
            reporting=_DoctrineReportingConfig(detail_level=_EnumLike("high")),
        )
        # Optional alternate profile for robustness in mixed test environments.
        self._profiles["balanced"] = DoctrineProfile(
            name="balanced",
            confidence=_DoctrineConfidenceConfig(
                alert_confidence_threshold=0.50,
                conservative_factor=1.00,
            ),
            engagement=_DoctrineEngagementConfig(escalation_tolerance=_EnumLike("neutral")),
            reporting=_DoctrineReportingConfig(detail_level=_EnumLike("medium")),
        )

    def activate(self, name: str, reason: str = "") -> None:
        if name not in self._profiles:
            raise ValueError(f"Unknown doctrine profile: {name}")
        self._active_name = name

    def get_active(self) -> Optional[DoctrineProfile]:
        if not self._active_name:
            return None
        return self._profiles.get(self._active_name)


class PolicyBiasEngine:
    """Applies doctrine policy to confidence while preserving raw evidence."""

    def __init__(self, profile: Optional[DoctrineProfile]) -> None:
        self.profile = profile

    def apply_confidence_bias(self, raw_score: float, domain: str, source_count: int) -> BiasResult:
        raw = max(0.0, min(1.0, float(raw_score)))
        adjustments: List[_BiasAdjustment] = []
        adjusted = raw

        if self.profile:
            factor = self.profile.confidence.conservative_factor
            # Tactical intent: higher source count slightly stabilizes confidence.
            source_stability_bonus = min(0.06, max(0, source_count - 1) * 0.01)
            adjusted = raw * factor + source_stability_bonus
            adjustments.append(
                _BiasAdjustment(
                    kind="conservative_factor",
                    detail=f"Applied {factor:.2f} in {domain} domain",
                    delta=adjusted - raw,
                )
            )

        adjusted = max(0.0, min(1.0, adjusted))
        return BiasResult(raw_value=raw, adjusted_value=adjusted, adjustments=adjustments)

    def should_alert(self, confidence: float, domain: str) -> bool:
        if self.profile:
            return confidence >= self.profile.confidence.alert_confidence_threshold
        return confidence >= 0.5

    def should_escalate(self, confidence: float, threat_level: str) -> bool:
        high_threat = threat_level.lower() in {"high", "critical"}
        if not high_threat:
            return False
        threshold = 0.72
        if self.profile and "conservative" in self.profile.engagement.escalation_tolerance.value:
            threshold = 0.75
        return confidence >= threshold


# =====================================================================
# Fallback Threat-Genome Correlator Layer
# =====================================================================


@dataclass
class GenomeObservation:
    """Normalized observation used for defensive actor-correlation."""

    observation_id: str
    source_type: str
    source_id: str
    timestamp: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    behavior_tags: List[str] = field(default_factory=list)
    raw_confidence: float = 0.5
    classification: str = ""
    threat_level: str = "unknown"


@dataclass
class CorrelationVerdict:
    """Outcome of correlation decision against known threat genomes."""

    observation_id: str
    decision: str  # "matched" | "created"
    composite_score: float
    matched_genome_id: Optional[str] = None
    matched_genome_name: Optional[str] = None
    created_genome_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "decision": self.decision,
            "composite_score": round(self.composite_score, 4),
            "matched_genome_id": self.matched_genome_id,
            "matched_genome_name": self.matched_genome_name,
            "created_genome_id": self.created_genome_id,
        }


class GenomeStore:
    """Adapter around ThreatGenomeStore with compatibility helper methods."""

    def __init__(self) -> None:
        self._store = ThreatGenomeStore()

    def add_genome(self, genome: ThreatGenome) -> None:
        self._store.add_genome(genome)

    def upsert_genome(self, genome: ThreatGenome) -> None:
        self._store.upsert_genome(genome)

    def list_genomes(self) -> List[ThreatGenome]:
        return self._store.list_genomes()

    def get_recently_active(self, hours: float = 24.0) -> List[ThreatGenome]:
        return self._store.recently_active(since_hours=hours)

    def count(self) -> int:
        return len(self._store)

    def stats(self) -> Dict[str, Any]:
        genomes = self._store.list_genomes()
        return {
            "count": len(genomes),
            "recent_24h": len(self._store.recently_active(since_hours=24)),
        }


class ThreatGenomeCorrelator:
    """Simple correlator for operational runtime integration and testing."""

    def __init__(self, genome_store: GenomeStore) -> None:
        self._store = genome_store

    def _score(self, observation: GenomeObservation, genome: ThreatGenome) -> float:
        obs_tags = {tag.strip().lower() for tag in observation.behavior_tags if tag}
        if observation.classification:
            obs_tags.add(observation.classification.strip().lower())
        genome_tags = {tag.strip().lower() for tag in genome.tags}
        if not obs_tags and not genome_tags:
            return 0.0
        intersection = len(obs_tags & genome_tags)
        union = len(obs_tags | genome_tags) or 1
        tag_score = intersection / union
        conf_bonus = 0.1 * max(0.0, min(1.0, observation.raw_confidence))
        return max(0.0, min(1.0, tag_score + conf_bonus))

    def correlate(self, observation: GenomeObservation) -> CorrelationVerdict:
        best: Optional[ThreatGenome] = None
        best_score = 0.0
        for genome in self._store.list_genomes():
            score = self._score(observation, genome)
            if score > best_score:
                best, best_score = genome, score

        if best and best_score >= 0.45:
            return CorrelationVerdict(
                observation_id=observation.observation_id,
                decision="matched",
                composite_score=best_score,
                matched_genome_id=best.actor_id,
                matched_genome_name=best.actor_name,
            )

        classification = (observation.classification or "unknown_contact").strip() or "unknown_contact"
        actor_id = f"gen-{uuid.uuid4().hex[:8]}"
        new_genome = ThreatGenome(
            actor_id=actor_id,
            actor_name=classification,
            actor_type="unknown",
            tags={classification.lower(), *(t.lower() for t in observation.behavior_tags)},
        )
        self._store.add_genome(new_genome)
        return CorrelationVerdict(
            observation_id=observation.observation_id,
            decision="created",
            composite_score=max(best_score, 0.50),
            created_genome_id=actor_id,
            matched_genome_name=classification,
        )


# =====================================================================
# Fallback Live Simulation Mirror Layer
# =====================================================================


@dataclass
class PredictedStateFrame:
    """Future-state hypothesis routed to mirror for later validation."""

    entity_id: str
    prediction_timestamp: datetime
    target_timestamp: datetime
    horizon_s: float
    predicted_position: Tuple[float, float, float]
    predicted_velocity: Tuple[float, float, float]
    predicted_heading_deg: float
    predicted_speed_mps: float
    predicted_threat_level: str
    predicted_label: str
    predicted_confidence: float
    bundle_id: str
    hypothesis_id: str


@dataclass
class ObservedStateFrame:
    """Observed real-world state used to validate previously predicted frames."""

    entity_id: str
    observation_timestamp: datetime
    observed_position: Tuple[float, float, float]
    observed_heading_deg: float
    observed_speed_mps: float
    observed_threat_level: str
    entity_present: bool = True


@dataclass
class ValidationMetric:
    """Aggregate validation quality metrics from mirror comparisons."""

    total_comparisons: int = 0
    mean_position_error_m: float = 0.0
    mean_heading_error_deg: float = 0.0
    mean_speed_error_mps: float = 0.0
    match_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_comparisons": self.total_comparisons,
            "mean_position_error_m": round(self.mean_position_error_m, 3),
            "mean_heading_error_deg": round(self.mean_heading_error_deg, 3),
            "mean_speed_error_mps": round(self.mean_speed_error_mps, 3),
            "match_rate": round(self.match_rate, 4),
        }


class LiveSimulationMirror:
    """Stores forecast frames and validates them against observed outcomes."""

    def __init__(self) -> None:
        self._predictions: List[PredictedStateFrame] = []
        self._observations: List[ObservedStateFrame] = []
        self._comparisons: List[Dict[str, float]] = []

    def record_prediction(self, frame: PredictedStateFrame) -> None:
        self._predictions.append(frame)

    def record_observation(self, obs: ObservedStateFrame) -> None:
        self._observations.append(obs)
        # Tactical matching strategy: best-time match per entity with smallest horizon gap.
        candidates = [p for p in self._predictions if p.entity_id == obs.entity_id]
        if not candidates:
            return
        best = min(
            candidates,
            key=lambda p: abs((p.target_timestamp - obs.observation_timestamp).total_seconds()),
        )
        dx = best.predicted_position[0] - obs.observed_position[0]
        dy = best.predicted_position[1] - obs.observed_position[1]
        dz = best.predicted_position[2] - obs.observed_position[2]
        pos_err = math.sqrt(dx * dx + dy * dy + dz * dz)
        heading_err = abs((best.predicted_heading_deg - obs.observed_heading_deg + 180.0) % 360.0 - 180.0)
        speed_err = abs(best.predicted_speed_mps - obs.observed_speed_mps)
        self._comparisons.append(
            {
                "position_error_m": pos_err,
                "heading_error_deg": heading_err,
                "speed_error_mps": speed_err,
                "threat_match": 1.0 if best.predicted_threat_level == obs.observed_threat_level else 0.0,
            }
        )
        try:
            self._predictions.remove(best)
        except ValueError:
            pass

    def get_validation_metrics(self) -> ValidationMetric:
        total = len(self._comparisons)
        if total == 0:
            return ValidationMetric()
        pos = sum(c["position_error_m"] for c in self._comparisons) / total
        head = sum(c["heading_error_deg"] for c in self._comparisons) / total
        speed = sum(c["speed_error_mps"] for c in self._comparisons) / total
        match = sum(c["threat_match"] for c in self._comparisons) / total
        return ValidationMetric(
            total_comparisons=total,
            mean_position_error_m=pos,
            mean_heading_error_deg=head,
            mean_speed_error_mps=speed,
            match_rate=match,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "total_frames": len(self._predictions) + len(self._observations),
            "pending_predictions": len(self._predictions),
            "observations_recorded": len(self._observations),
            "total_comparisons": len(self._comparisons),
        }


# =====================================================================
# Fallback Learning Layer
# =====================================================================


@dataclass
class FeedbackBatch:
    """Learning feedback batch generated from mirror validation metrics."""

    batch_id: str = field(default_factory=lambda: f"fb-{uuid.uuid4().hex[:8]}")
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    insights: Dict[str, Any] = field(default_factory=dict)


class FeedbackSignalGenerator:
    """Produces lightweight feedback signals from recent mirror performance."""

    def __init__(
        self,
        mirror: LiveSimulationMirror,
        calibrator: ConfidenceCalibrator,
        pattern_memory: PatternMemory,
    ) -> None:
        self._mirror = mirror
        self._calibrator = calibrator
        self._pattern_memory = pattern_memory

    def analyze(self) -> FeedbackBatch:
        metrics = self._mirror.get_validation_metrics().to_dict()
        quality = 1.0 - min(1.0, metrics["mean_position_error_m"] / 1000.0)
        if hasattr(self._calibrator, "calibrate"):
            quality = self._calibrator.calibrate(quality)  # type: ignore[attr-defined]
        return FeedbackBatch(
            insights={
                "validation_metrics": metrics,
                "forecast_quality": round(float(quality), 4),
            }
        )


# =====================================================================
# Operational Picture (output objects)
# =====================================================================


@dataclass
class EntityPicture:
    """One entity's complete intelligence picture."""

    entity_id: str = ""
    entity_type: str = ""
    classification: str = ""
    allegiance: str = "unknown"

    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    speed_mps: float = 0.0
    threat_level: str = "unknown"
    raw_confidence: float = 0.5

    doctrine_adjusted_confidence: float = 0.5
    doctrine_adjustments: List[Dict[str, Any]] = field(default_factory=list)

    genome_id: Optional[str] = None
    genome_actor_name: Optional[str] = None
    genome_correlation_score: float = 0.0
    genome_verdict: Optional[str] = None

    forecast_bundle_id: Optional[str] = None
    forecast_trend: str = "unknown"
    forecast_dominant_30s: Optional[str] = None
    forecast_dominant_2min: Optional[str] = None
    forecast_confidence: float = 0.0

    should_alert: bool = False
    should_escalate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "classification": self.classification,
            "allegiance": self.allegiance,
            "position": list(self.position),
            "heading_deg": round(self.heading_deg, 1),
            "speed_mps": round(self.speed_mps, 2),
            "threat_level": self.threat_level,
            "raw_confidence": round(self.raw_confidence, 4),
            "doctrine_adjusted_confidence": round(self.doctrine_adjusted_confidence, 4),
            "doctrine_adjustments": self.doctrine_adjustments,
            "genome_id": self.genome_id,
            "genome_actor_name": self.genome_actor_name,
            "genome_correlation_score": round(self.genome_correlation_score, 4),
            "forecast_trend": self.forecast_trend,
            "forecast_dominant_30s": self.forecast_dominant_30s,
            "forecast_dominant_2min": self.forecast_dominant_2min,
            "forecast_confidence": round(self.forecast_confidence, 4),
            "should_alert": self.should_alert,
            "should_escalate": self.should_escalate,
        }


@dataclass
class OperationalPicture:
    """Top-level structured output consumed by dashboards and operators."""

    picture_id: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entities: List[EntityPicture] = field(default_factory=list)
    entity_count: int = 0

    active_genomes: List[Dict[str, Any]] = field(default_factory=list)
    genome_correlations: List[Dict[str, Any]] = field(default_factory=list)
    forecast_bundles: List[Dict[str, Any]] = field(default_factory=list)

    active_doctrine: Optional[str] = None
    doctrine_profile_summary: Optional[Dict[str, Any]] = None

    mirror_status: Optional[Dict[str, Any]] = None
    validation_metrics: Optional[Dict[str, Any]] = None

    mean_confidence: float = 0.0
    entities_above_alert_threshold: int = 0
    entities_requiring_escalation: int = 0

    processing_steps: List[str] = field(default_factory=list)
    audit_notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.picture_id:
            self.picture_id = f"oppic-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "picture_id": self.picture_id,
            "generated_at": self.generated_at.isoformat(),
            "entity_count": self.entity_count,
            "entities": [entity.to_dict() for entity in self.entities],
            "active_genomes": self.active_genomes,
            "genome_correlations": self.genome_correlations,
            "forecast_bundles": self.forecast_bundles,
            "active_doctrine": self.active_doctrine,
            "doctrine_profile_summary": self.doctrine_profile_summary,
            "mirror_status": self.mirror_status,
            "validation_metrics": self.validation_metrics,
            "mean_confidence": round(self.mean_confidence, 4),
            "entities_above_alert_threshold": self.entities_above_alert_threshold,
            "entities_requiring_escalation": self.entities_requiring_escalation,
            "processing_steps": self.processing_steps,
            "audit_notes": self.audit_notes,
        }


# =====================================================================
# Operational Picture Service
# =====================================================================


class OperationalPictureService:
    """Thin coordinator that composes all optional intelligence subsystems."""

    def __init__(
        self,
        predictor: Optional[ShortHorizonPredictor] = None,
        genome_store: Optional[GenomeStore] = None,
        genome_correlator: Optional[ThreatGenomeCorrelator] = None,
        doctrine_manager: Optional[DoctrineProfileManager] = None,
        bias_engine: Optional[PolicyBiasEngine] = None,
        mirror: Optional[LiveSimulationMirror] = None,
        feedback_generator: Optional[FeedbackSignalGenerator] = None,
    ) -> None:
        self.predictor = predictor
        self.genome_store = genome_store
        self.genome_correlator = genome_correlator
        self.doctrine_manager = doctrine_manager
        self.bias_engine = bias_engine
        self.mirror = mirror
        self.feedback_generator = feedback_generator
        self._picture_count = 0

    @classmethod
    def build_default(cls) -> "OperationalPictureService":
        """Factory wiring all available subsystems with Saudi/GCC defaults."""
        pattern_memory = PatternMemory()
        if hasattr(pattern_memory, "register_defaults"):
            pattern_memory.register_defaults()

        calibrator = ConfidenceCalibrator()

        # Some S3M variants accept calibrator/pattern memory; this repo's predictor does not.
        try:
            predictor = ShortHorizonPredictor(  # type: ignore[call-arg]
                pattern_memory=pattern_memory,
                calibrator=calibrator,
            )
        except TypeError:
            predictor = ShortHorizonPredictor()

        genome_store = GenomeStore()
        genome_correlator = ThreatGenomeCorrelator(genome_store)

        doctrine_manager = DoctrineProfileManager()
        doctrine_manager.register_builtin_profiles()
        doctrine_manager.activate("saudi_gulf_defensive", reason="Default startup")
        bias_engine = PolicyBiasEngine(doctrine_manager.get_active())

        mirror = LiveSimulationMirror()
        feedback_generator = FeedbackSignalGenerator(mirror, calibrator, pattern_memory)

        return cls(
            predictor=predictor,
            genome_store=genome_store,
            genome_correlator=genome_correlator,
            doctrine_manager=doctrine_manager,
            bias_engine=bias_engine,
            mirror=mirror,
            feedback_generator=feedback_generator,
        )

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def process_entities(
        self,
        entities: List[EntitySnapshot],
        windows_s: Optional[List[float]] = None,
    ) -> OperationalPicture:
        """Run the full intelligence pipeline on current fused entities."""
        picture = OperationalPicture()
        steps: List[str] = ["pipeline_started"]
        audit: List[str] = []
        entity_pictures: List[EntityPicture] = []
        all_forecasts: List[Dict[str, Any]] = []
        all_verdicts: List[Dict[str, Any]] = []

        windows = windows_s or [30.0, 120.0, 600.0]
        doctrine_bias = self._get_doctrine_bias()

        for entity in entities:
            ep = EntityPicture(
                entity_id=entity.entity_id,
                entity_type=entity.entity_type,
                classification=entity.classification,
                allegiance=entity.allegiance,
                position=entity.position,
                velocity=entity.velocity,
                heading_deg=entity.heading_deg,
                speed_mps=entity.speed_mps,
                threat_level=entity.threat_level,
                raw_confidence=entity.confidence,
                doctrine_adjusted_confidence=entity.confidence,
            )

            verdict = self._correlate_genome(entity)
            if verdict:
                ep.genome_id = verdict.matched_genome_id or verdict.created_genome_id
                ep.genome_actor_name = verdict.matched_genome_name
                ep.genome_correlation_score = verdict.composite_score
                ep.genome_verdict = verdict.decision
                all_verdicts.append(verdict.to_dict())

            bundle = self._run_prediction(entity, windows, doctrine_bias)
            if bundle:
                ep.forecast_bundle_id = bundle.bundle_id
                ep.forecast_trend = bundle.overall_trend.value
                ep.forecast_confidence = bundle.forecast_confidence
                w30 = bundle.get_window(30.0)
                if w30 and w30.dominant:
                    ep.forecast_dominant_30s = w30.dominant.label
                w120 = bundle.get_window(120.0)
                if w120 and w120.dominant:
                    ep.forecast_dominant_2min = w120.dominant.label
                all_forecasts.append(bundle.to_dict())
                self._feed_mirror(entity, bundle)

            bias_result = self._apply_doctrine(entity)
            if bias_result:
                ep.doctrine_adjusted_confidence = bias_result.adjusted_value
                ep.doctrine_adjustments = [adj.to_dict() for adj in bias_result.adjustments]
                ep.should_alert = self._check_alert(bias_result.adjusted_value, entity)
                ep.should_escalate = self._check_escalate(bias_result.adjusted_value, entity)

            entity_pictures.append(ep)

        steps.append(f"processed_{len(entities)}_entities")

        picture.entities = entity_pictures
        picture.entity_count = len(entity_pictures)
        picture.forecast_bundles = all_forecasts
        picture.genome_correlations = all_verdicts

        if self.genome_store:
            picture.active_genomes = [g.to_dict() for g in self.genome_store.get_recently_active(hours=24)]

        if self.doctrine_manager:
            active = self.doctrine_manager.get_active()
            if active:
                picture.active_doctrine = active.name
                picture.doctrine_profile_summary = {
                    "name": active.name,
                    "escalation_tolerance": active.engagement.escalation_tolerance.value,
                    "detail_level": active.reporting.detail_level.value,
                    "alert_threshold": active.confidence.alert_confidence_threshold,
                    "conservative_factor": active.confidence.conservative_factor,
                }

        if self.mirror:
            picture.mirror_status = self.mirror.stats()
            picture.validation_metrics = self.mirror.get_validation_metrics().to_dict()

        if entity_pictures:
            confs = [ep.doctrine_adjusted_confidence for ep in entity_pictures]
            picture.mean_confidence = sum(confs) / len(confs)
            picture.entities_above_alert_threshold = sum(1 for ep in entity_pictures if ep.should_alert)
            picture.entities_requiring_escalation = sum(1 for ep in entity_pictures if ep.should_escalate)

        steps.append("picture_composed")

        if self.genome_correlator:
            audit.append(f"Genome correlations: {len(all_verdicts)}")
        if self.predictor:
            audit.append(f"Forecasts generated: {len(all_forecasts)}")
        if self.bias_engine and self.bias_engine.profile:
            audit.append(f"Doctrine applied: {self.bias_engine.profile.name}")
        if self.mirror:
            audit.append(f"Mirror frames: {self.mirror.stats()['total_frames']}")

        picture.processing_steps = steps
        picture.audit_notes = audit
        self._picture_count += 1
        return picture

    # ------------------------------------------------------------------
    # Observation recording (mirror validation)
    # ------------------------------------------------------------------

    def record_observations(self, observations: Sequence[ObservedStateFrame]) -> int:
        """Record real observations for mirror comparison."""
        if not self.mirror:
            return 0
        count = 0
        for obs in observations:
            self.mirror.record_observation(obs)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Feedback cycle
    # ------------------------------------------------------------------

    def run_feedback_cycle(self) -> Optional[FeedbackBatch]:
        """Run one learning feedback cycle and return generated batch."""
        if self.feedback_generator:
            return self.feedback_generator.analyze()
        return None

    # ------------------------------------------------------------------
    # Subsystem delegation
    # ------------------------------------------------------------------

    def _correlate_genome(self, entity: EntitySnapshot) -> Optional[CorrelationVerdict]:
        if not self.genome_correlator:
            return None
        obs = GenomeObservation(
            observation_id=f"oppic-{entity.entity_id}",
            source_type="operational_picture",
            source_id=entity.entity_id,
            timestamp=entity.last_updated,
            latitude=entity.position[0] if len(entity.position) > 0 else None,
            longitude=entity.position[1] if len(entity.position) > 1 else None,
            behavior_tags=list(entity.behavior_tags),
            raw_confidence=entity.confidence,
            classification=entity.classification,
            threat_level=entity.threat_level,
        )
        return self.genome_correlator.correlate(obs)

    def _run_prediction(
        self,
        entity: EntitySnapshot,
        windows: List[float],
        doctrine_bias: Optional[str],
    ) -> Optional[ForecastBundle]:
        if not self.predictor:
            return None
        return self.predictor.forecast(entity, windows_s=windows, doctrine_bias=doctrine_bias)

    def _apply_doctrine(self, entity: EntitySnapshot) -> Optional[BiasResult]:
        if not self.bias_engine:
            return None
        domain = self._infer_domain(entity)
        return self.bias_engine.apply_confidence_bias(
            raw_score=entity.confidence,
            domain=domain,
            source_count=max(1, entity.history_depth),
        )

    def _feed_mirror(self, entity: EntitySnapshot, bundle: ForecastBundle) -> None:
        if not self.mirror:
            return
        for window in bundle.windows:
            dominant = window.dominant
            if not dominant:
                continue
            frame = PredictedStateFrame(
                entity_id=entity.entity_id,
                prediction_timestamp=datetime.now(timezone.utc),
                target_timestamp=datetime.now(timezone.utc) + timedelta(seconds=window.window_seconds),
                horizon_s=window.window_seconds,
                predicted_position=dominant.predicted_state.predicted_position,
                predicted_velocity=dominant.predicted_state.predicted_velocity,
                predicted_heading_deg=dominant.predicted_state.predicted_heading_deg,
                predicted_speed_mps=dominant.predicted_state.predicted_speed_mps,
                predicted_threat_level=dominant.predicted_state.predicted_threat_level,
                predicted_label=dominant.label,
                predicted_confidence=dominant.probability,
                bundle_id=bundle.bundle_id,
                hypothesis_id=dominant.hypothesis_id,
            )
            self.mirror.record_prediction(frame)

    def _check_alert(self, confidence: float, entity: EntitySnapshot) -> bool:
        if self.bias_engine:
            return self.bias_engine.should_alert(confidence, self._infer_domain(entity))
        return confidence >= 0.5

    def _check_escalate(self, confidence: float, entity: EntitySnapshot) -> bool:
        if self.bias_engine:
            return self.bias_engine.should_escalate(confidence, entity.threat_level)
        return entity.threat_level in {"critical", "high"} and confidence >= 0.7

    def _get_doctrine_bias(self) -> Optional[str]:
        if not self.doctrine_manager:
            return None
        active = self.doctrine_manager.get_active()
        if not active:
            return None
        tolerance = active.engagement.escalation_tolerance.value
        if "conservative" in tolerance:
            return "defensive"
        if "permissive" in tolerance:
            return "aggressive"
        return "neutral"

    @staticmethod
    def _infer_domain(entity: EntitySnapshot) -> str:
        etype = entity.entity_type.lower()
        if any(key in etype for key in ("aircraft", "uav", "drone", "air")):
            return "airspace"
        if any(key in etype for key in ("ship", "vessel", "maritime", "boat")):
            return "maritime"
        if any(key in etype for key in ("vehicle", "ground", "infantry")):
            return "ground"
        if any(key in etype for key in ("cyber", "network")):
            return "cyber"
        return "unknown"

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "pictures_generated": self._picture_count,
            "genome_store": self.genome_store.stats() if self.genome_store else None,
            "mirror": self.mirror.stats() if self.mirror else None,
            "doctrine_active": (
                self.doctrine_manager.get_active().name
                if self.doctrine_manager and self.doctrine_manager.get_active()
                else None
            ),
        }

