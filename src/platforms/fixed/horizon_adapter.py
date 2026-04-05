"""Horizon fixed-site adapter and local track-store for COP fusion."""

from __future__ import annotations

from datetime import datetime, timezone
import math

from src.platforms.common.messages import PlatformState, PlatformType, Track


class HorizonAdapter:
    """Offline simulation adapter for a fixed overwatch node."""

    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self._connected = False
        self._position = (0.0, 0.0, 0.0)

    def connect(self) -> bool:
        self._connected = True
        return True

    def read_state(self) -> PlatformState:
        return PlatformState(
            platform_id=self.platform_id,
            platform_type=PlatformType.FIXED,
            position=self._position,
        )


class TrackStore:
    """Simple local track store with association, merge, and staleness aging."""

    def __init__(self, association_distance_m: float = 75.0, max_track_age_s: float = 30.0) -> None:
        if association_distance_m <= 0.0:
            raise ValueError("association_distance_m must be > 0")
        if max_track_age_s <= 0.0:
            raise ValueError("max_track_age_s must be > 0")
        self.association_distance_m = association_distance_m
        self.max_track_age_s = max_track_age_s
        self._tracks: dict[str, Track] = {}

    def ingest_track(self, track: Track) -> None:
        """Ingest track update and merge nearby detections for COP stability."""
        nearest = self._nearest_track(track)
        if nearest is None:
            self._tracks[track.track_id] = track
            return

        distance = math.dist(nearest.position, track.position)
        if distance > self.association_distance_m:
            self._tracks[track.track_id] = track
            return

        # Weighted merge improves tactical continuity under sensor noise.
        total_conf = max(1e-6, nearest.confidence + track.confidence)
        merged_position = (
            ((nearest.position[0] * nearest.confidence) + (track.position[0] * track.confidence)) / total_conf,
            ((nearest.position[1] * nearest.confidence) + (track.position[1] * track.confidence)) / total_conf,
            ((nearest.position[2] * nearest.confidence) + (track.position[2] * track.confidence)) / total_conf,
        )
        nearest.position = merged_position
        nearest.confidence = min(1.0, max(nearest.confidence, track.confidence))
        nearest.last_seen = max(nearest.last_seen, track.last_seen)
        nearest.threat_priority = track.threat_priority
        if track.classification != "unknown":
            nearest.classification = track.classification

    def get_tracks(self) -> list[Track]:
        return list(self._tracks.values())

    def age_out(self, now: datetime | None = None) -> int:
        """Drop stale tracks to avoid acting on obsolete tactical contacts."""
        current_time = now or datetime.now(timezone.utc)
        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if (current_time - track.last_seen).total_seconds() > self.max_track_age_s
        ]
        for track_id in expired:
            del self._tracks[track_id]
        return len(expired)

    def _nearest_track(self, incoming: Track) -> Track | None:
        if not self._tracks:
            return None
        return min(self._tracks.values(), key=lambda existing: math.dist(existing.position, incoming.position))
