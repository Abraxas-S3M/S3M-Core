"""Threat evaluation pipeline for tactical engagement recommendations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from src.platforms.common import ROEProfile, ThreatPriority, Track


@dataclass
class EngagementRecommendation:
    """Recommended engagement action with ROE compliance disposition."""

    track_id: str
    recommended_effector: str | None
    roe_compliant: bool
    rationale: str


class ThreatPrioritizer:
    """Rank tracks by urgency using confidence, threat level, and proximity."""

    def __init__(self, default_reference_position: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        self.default_reference_position = default_reference_position

    def prioritize_tracks(
        self,
        tracks: list[Track],
        blue_force_positions: list[tuple[float, float, float]] | None = None,
    ) -> list[Track]:
        if not tracks:
            return []
        references = blue_force_positions or [self.default_reference_position]
        # Tactical context: nearest-hostile pressure is amplified to protect friendly forces.
        ranked = sorted(
            tracks,
            key=lambda track: self._composite_score(track=track, references=references),
            reverse=True,
        )
        return ranked

    def _composite_score(self, track: Track, references: list[tuple[float, float, float]]) -> float:
        priority = float(EngagementPipeline._priority_score(track.threat_priority))
        confidence = float(track.confidence)
        min_distance = min(math.dist(track.position, reference) for reference in references)
        proximity_score = 1.0 / (1.0 + (min_distance / 1000.0))
        return (priority * 0.6) + (confidence * 0.3) + (proximity_score * 0.1)


class EngagementPipeline:
    """Minimal deterministic threat-ranking pipeline for offline testing."""

    def __init__(self, roe_profile: ROEProfile = ROEProfile.WEAPONS_TIGHT) -> None:
        self.roe_profile = roe_profile

    def evaluate_threats(
        self,
        tracks: list[Track],
        available_effectors: dict[str, Any],
    ) -> list[EngagementRecommendation]:
        if not tracks:
            return []

        ranked = sorted(
            tracks,
            key=lambda t: (self._priority_score(t.threat_priority), t.confidence),
            reverse=True,
        )
        effector = next(iter(available_effectors.keys()), None)
        recommendations: list[EngagementRecommendation] = []
        for track in ranked:
            if track.confidence < 0.5:
                continue
            roe_ok = self._is_roe_compliant(track)
            recommendations.append(
                EngagementRecommendation(
                    track_id=track.track_id,
                    recommended_effector=effector,
                    roe_compliant=roe_ok,
                    rationale=f"priority={track.threat_priority.value}, confidence={track.confidence:.2f}",
                )
            )
        return recommendations

    @staticmethod
    def _priority_score(priority: ThreatPriority) -> int:
        mapping = {
            ThreatPriority.LOW: 1,
            ThreatPriority.MEDIUM: 2,
            ThreatPriority.HIGH: 3,
            ThreatPriority.CRITICAL: 4,
        }
        return mapping[priority]

    def _is_roe_compliant(self, track: Track) -> bool:
        """Apply simplified ROE gating suitable for smoke-test verification."""
        if self.roe_profile == ROEProfile.WEAPONS_HOLD:
            return False
        if self.roe_profile == ROEProfile.WEAPONS_TIGHT and track.classification.lower() in {"civilian", "friendly"}:
            return False
        return True
