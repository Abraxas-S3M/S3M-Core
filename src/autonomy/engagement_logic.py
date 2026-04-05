"""Threat evaluation pipeline for tactical engagement recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.platforms.common import ROEProfile, ThreatPriority, Track


@dataclass
class EngagementRecommendation:
    """Recommended engagement action with ROE compliance disposition."""

    track_id: str
    recommended_effector: str | None
    roe_compliant: bool
    rationale: str


class EngagementPipeline:
    """Minimal deterministic threat-ranking pipeline for offline testing."""

    def __init__(self, roe_profile: ROEProfile = ROEProfile.WEAPONS_TIGHT) -> None:
        self.roe_profile = roe_profile
        self.zone_roe_profiles: dict[str, ROEProfile] = {}

    def configure_zone_roe_profiles(
        self,
        *,
        default_profile: ROEProfile,
        zone_profiles: dict[str, ROEProfile],
    ) -> None:
        """Set default and per-zone ROE for mission-area fire control."""
        self.roe_profile = default_profile
        self.zone_roe_profiles = dict(zone_profiles)

    def resolve_roe_profile(self, zone_id: str | None = None) -> ROEProfile:
        if zone_id and zone_id in self.zone_roe_profiles:
            return self.zone_roe_profiles[zone_id]
        return self.roe_profile

    def evaluate_threats(
        self,
        tracks: list[Track],
        available_effectors: dict[str, Any],
        zone_id: str | None = None,
    ) -> list[EngagementRecommendation]:
        if not tracks:
            return []

        active_roe = self.resolve_roe_profile(zone_id)
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
            roe_ok = self._is_roe_compliant(track, active_roe)
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

    def _is_roe_compliant(self, track: Track, profile: ROEProfile) -> bool:
        """Apply simplified ROE gating suitable for smoke-test verification."""
        if profile == ROEProfile.WEAPONS_HOLD:
            return False
        if profile == ROEProfile.WEAPONS_TIGHT and track.classification.lower() in {"civilian", "friendly"}:
            return False
        return True
