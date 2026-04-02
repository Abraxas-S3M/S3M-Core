"""Short-horizon tactical predictor with optional pattern/certainty upgrades."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from .prediction_models import (
    EntitySnapshot,
    ExplanationBlock,
    ForecastBundle,
    ForecastWindow,
    PredictedEntityState,
    PredictionHypothesis,
    ThreatPosture,
    UncertaintyEstimate,
)
from .pattern_memory import PatternMemory, MotifMatch
from .confidence_calibrator import ConfidenceCalibrator


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


class ShortHorizonPredictor:
    """Generate deterministic short-horizon hypotheses for an entity.

    The implementation is intentionally lightweight for reliable edge execution.
    """

    def __init__(
        self,
        windows_s: Optional[List[float]] = None,
        top_hypotheses_per_window: int = 3,
        doctrine_bias: Optional[Dict[str, float]] = None,
        # Chunk 4: optional pattern memory and calibrator
        pattern_memory: Optional[PatternMemory] = None,
        calibrator: Optional[ConfidenceCalibrator] = None,
    ) -> None:
        self.windows_s = windows_s or [30.0, 60.0, 120.0]
        self.top_hypotheses_per_window = max(1, int(top_hypotheses_per_window))
        self.doctrine_bias = doctrine_bias or {}
        self.pattern_memory = pattern_memory
        self.calibrator = calibrator

    def forecast(self, entity: EntitySnapshot) -> ForecastBundle:
        """Build forecast windows for one entity snapshot."""
        trend = self._infer_trend(entity)
        vol = entity.volatility

        # Chunk 4: motif lookup
        best_motif_match: Optional[MotifMatch] = None
        motif_match_score = 0.0
        if self.pattern_memory:
            traits = self._extract_traits(entity)
            motif_matches = self.pattern_memory.lookup(
                traits,
                entity_type=entity.entity_type,
                entity_tags=set(entity.behavior_tags),
                top_k=1,
            )
            if motif_matches:
                best_motif_match = motif_matches[0]
                motif_match_score = best_motif_match.effective_score

        doctrine_bias = self.doctrine_bias.get(entity.entity_type.lower(), 1.0)
        windows: List[ForecastWindow] = []
        for w_s in self.windows_s:
            pw = self._forecast_window(
                entity,
                w_s,
                self.top_hypotheses_per_window,
                trend,
                vol,
                doctrine_bias,
                motif_match_score=motif_match_score,
                motif_name=best_motif_match.motif.name if best_motif_match else None,
            )
            windows.append(ForecastWindow(horizon_s=w_s, hypotheses=pw))

        return ForecastBundle(
            entity_id=entity.entity_id,
            windows=windows,
            overall_trend=trend,
            volatility_score=vol,
            forecast_confidence=self._overall_confidence(windows),
            matched_motif_name=best_motif_match.motif.name if best_motif_match else None,
            motif_match_score=motif_match_score,
            calibration_applied=self.calibrator is not None,
        )

    def _forecast_window(
        self,
        entity: EntitySnapshot,
        horizon_s: float,
        n_hyp: int,
        trend: ThreatPosture,
        vol: float,
        doctrine_bias: float,
        motif_match_score: float = 0.0,
        motif_name: Optional[str] = None,
    ) -> List[PredictionHypothesis]:
        branch = self._branch_probabilities(entity, trend, horizon_s, vol)
        sorted_branch = sorted(branch.items(), key=lambda kv: kv[1], reverse=True)[:n_hyp]

        out: List[PredictionHypothesis] = []
        for label, base_prob in sorted_branch:
            prob = _clamp(base_prob * doctrine_bias)
            predicted = self._project_state(entity, label, horizon_s)
            unc = self._estimate_uncertainty(entity, horizon_s, vol)
            expl = ExplanationBlock(
                summary=f"{label} projected over {int(horizon_s)}s",
                factors={
                    "base_prob": base_prob,
                    "volatility": vol,
                    "doctrine_bias": doctrine_bias,
                    "motif_match": motif_match_score,
                },
                evidence=[f"trend={trend.value}", f"history_depth={entity.history_depth}"],
            )
            hyp = PredictionHypothesis(
                label=label,
                probability=prob,
                predicted_state=predicted,
                uncertainty=unc,
                explanation=expl,
                raw_probability=prob,
                matched_motif=motif_name,
            )

            if self.calibrator:
                heading_var = _variance([h.heading_deg for h in entity.history[-10:]]) if entity.history else 0.0
                speed_var = _variance([h.speed_mps for h in entity.history[-10:]]) if entity.history else 0.0
                threat_changes = self._count_threat_changes(entity)
                cal = self.calibrator.calibrate(
                    raw_score=prob,
                    entity_confidence=entity.confidence,
                    history_depth=entity.history_depth,
                    heading_variance=heading_var,
                    speed_variance=speed_var,
                    threat_level_changes=threat_changes,
                    pattern_match_score=motif_match_score,
                    horizon_s=horizon_s,
                    source_reliability=entity.confidence,
                )
                hyp.calibrated_confidence = cal.to_dict()
                hyp.probability = prob * 0.6 + cal.calibrated_score * 0.4

            out.append(hyp)
        return out

    def _branch_probabilities(
        self,
        entity: EntitySnapshot,
        trend: ThreatPosture,
        horizon_s: float,
        vol: float,
    ) -> Dict[str, float]:
        """Compute branch probabilities for major tactical continuations."""
        del entity  # API compatibility; current branch model uses trend/volatility.
        horizon_scale = min(1.0, max(0.25, 120.0 / max(1.0, horizon_s)))
        vol_penalty = max(0.6, 1.0 - vol * 0.4)
        if trend == ThreatPosture.ESCALATING:
            base = {"continue_course": 0.35, "accelerate": 0.45, "decelerate": 0.20}
        elif trend == ThreatPosture.DEESCALATING:
            base = {"continue_course": 0.45, "accelerate": 0.15, "decelerate": 0.40}
        else:
            base = {"continue_course": 0.55, "accelerate": 0.20, "decelerate": 0.25}

        weighted = {
            "continue_course": base["continue_course"] * (0.9 + 0.1 * horizon_scale),
            "accelerate": base["accelerate"] * vol_penalty,
            "decelerate": base["decelerate"] * (2.0 - vol_penalty),
        }
        total = sum(weighted.values()) or 1.0
        return {k: v / total for k, v in weighted.items()}

    def _project_state(self, entity: EntitySnapshot, label: str, horizon_s: float) -> PredictedEntityState:
        """Project simple kinematics for each hypothesis branch."""
        speed = entity.speed_mps
        if label == "accelerate":
            speed = speed * 1.15
        elif label == "decelerate":
            speed = speed * 0.75

        heading_rad = math.radians(entity.heading_deg)
        dx = speed * horizon_s * math.cos(heading_rad)
        dy = speed * horizon_s * math.sin(heading_rad)
        z = entity.position[2]
        if label == "accelerate":
            z += min(20.0, horizon_s * 0.05)
        elif label == "decelerate":
            z -= min(20.0, horizon_s * 0.05)

        tags = list(entity.behavior_tags)
        if label not in tags:
            tags.append(label)
        return PredictedEntityState(
            horizon_s=horizon_s,
            position=(entity.position[0] + dx, entity.position[1] + dy, z),
            speed_mps=speed,
            heading_deg=entity.heading_deg,
            threat_level=entity.threat_level,
            behavior_tags=tags,
        )

    def _estimate_uncertainty(self, entity: EntitySnapshot, horizon_s: float, vol: float) -> UncertaintyEstimate:
        depth_factor = 1.0 - min(0.7, entity.history_depth * 0.05)
        horizon_factor = min(1.0, horizon_s / 240.0)
        aleatoric = _clamp(0.08 + vol * 0.25 + horizon_factor * 0.2, 0.01, 0.95)
        epistemic = _clamp(0.10 + depth_factor * 0.4, 0.01, 0.95)
        width = _clamp(0.10 + aleatoric * 0.2 + epistemic * 0.2, 0.05, 0.45)
        center = _clamp(entity.confidence * 0.5 + 0.25)
        return UncertaintyEstimate(
            aleatoric=aleatoric,
            epistemic=epistemic,
            interval_low=_clamp(center - width),
            interval_high=_clamp(center + width),
        )

    def _infer_trend(self, entity: EntitySnapshot) -> ThreatPosture:
        """Infer trajectory trend from recent threat levels or speed profile."""
        if entity.history_depth >= 2:
            threat_numeric = {"low": 1, "guarded": 2, "medium": 2, "elevated": 3, "high": 4, "critical": 5}
            first = threat_numeric.get(entity.history[-2].threat_level.lower(), 2)
            last = threat_numeric.get(entity.history[-1].threat_level.lower(), 2)
            if last > first:
                return ThreatPosture.ESCALATING
            if last < first:
                return ThreatPosture.DEESCALATING

            recent_speeds = [h.speed_mps for h in entity.history[-5:]]
            if len(recent_speeds) >= 3 and recent_speeds[-1] > recent_speeds[0] * 1.15:
                return ThreatPosture.ESCALATING
            if len(recent_speeds) >= 3 and recent_speeds[-1] < recent_speeds[0] * 0.85:
                return ThreatPosture.DEESCALATING
            return ThreatPosture.STABLE
        return ThreatPosture.UNKNOWN

    @staticmethod
    def _extract_traits(entity: EntitySnapshot) -> Dict[str, Any]:
        traits: Dict[str, Any] = {"speed_range_mps": entity.speed_mps}
        if entity.history and len(entity.history) >= 3:
            headings = [h.heading_deg for h in entity.history[-10:]]
            speeds = [h.speed_mps for h in entity.history[-10:]]
            traits["heading_variance_deg"] = _variance(headings)
            traits["speed_variance_mps"] = _variance(speeds)
            alts = [h.position[2] for h in entity.history[-10:]]
            traits["altitude_stable"] = _variance(alts) < 25.0
            if len(entity.history) >= 2:
                d_first = math.sqrt(entity.history[0].position[0] ** 2 + entity.history[0].position[1] ** 2)
                d_last = math.sqrt(entity.position[0] ** 2 + entity.position[1] ** 2)
                traits["closing"] = d_last < d_first
                traits["moving_away"] = d_last > d_first
        else:
            traits["heading_variance_deg"] = 0.0
        traits["high_speed"] = entity.speed_mps > 30.0
        return traits

    @staticmethod
    def _count_threat_changes(entity: EntitySnapshot) -> int:
        if len(entity.history) < 2:
            return 0
        changes = 0
        prev = entity.history[0].threat_level
        for h in entity.history[1:]:
            if h.threat_level != prev:
                changes += 1
                prev = h.threat_level
        return changes

    def _overall_confidence(self, windows: List[ForecastWindow]) -> float:
        probs: List[float] = []
        for window in windows:
            if not window.hypotheses:
                continue
            probs.append(max(h.probability for h in window.hypotheses))
        if not probs:
            return 0.5
        return _clamp(sum(probs) / len(probs), 0.01, 0.99)
