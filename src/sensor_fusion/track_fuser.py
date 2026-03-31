"""Multi-sensor track association and fusion for tactical awareness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import inf
from typing import Dict, List, Optional
from uuid import uuid4

from src.sensor_fusion.ekf_filter import EKFFilter
from src.sensor_fusion.models import SensorReading, Track, TrackState


@dataclass
class _TrackContext:
    """Internal runtime metadata used for track lifecycle management."""

    updates: int = 0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ekf: EKFFilter = field(default_factory=EKFFilter)


class TrackFuser:
    """Fuse readings into stable tracks for battlefield object continuity."""

    def __init__(self, association_threshold: float = 50.0, max_tracks: int = 1000) -> None:
        if not isinstance(association_threshold, (int, float)) or association_threshold <= 0:
            raise ValueError("association_threshold must be a positive number")
        if not isinstance(max_tracks, int) or max_tracks <= 0:
            raise ValueError("max_tracks must be a positive integer")
        self.association_threshold = float(association_threshold)
        self.max_tracks = max_tracks
        self._tracks: Dict[str, Track] = {}
        self._ctx: Dict[str, _TrackContext] = {}

    def _nearest_track(self, reading: SensorReading) -> Optional[Track]:
        if reading.position is None:
            return None
        nearest: Optional[Track] = None
        best_distance = inf
        for track in self._tracks.values():
            if track.state == TrackState.DELETED:
                continue
            distance = track.distance_to(
                Track(
                    track_id="probe",
                    state=TrackState.TENTATIVE,
                    position=reading.position,
                    velocity=(0.0, 0.0, 0.0),
                    covariance=[[0.0] * 6 for _ in range(6)],
                    last_update=reading.timestamp,
                    sensor_sources=[],
                )
            )
            if distance < best_distance:
                best_distance = distance
                nearest = track
        if nearest and best_distance <= self.association_threshold:
            return nearest
        return None

    def _create_track(self, reading: SensorReading) -> Track:
        if reading.position is None:
            raise ValueError("reading.position is required to create a fused track")
        if len(self._tracks) >= self.max_tracks:
            # Tactical data retention policy: drop oldest deleted/lost first.
            removable = sorted(self._tracks.values(), key=lambda t: t.last_update)
            for candidate in removable:
                if candidate.state in {TrackState.DELETED, TrackState.LOST}:
                    self._tracks.pop(candidate.track_id, None)
                    self._ctx.pop(candidate.track_id, None)
                    break
        track_id = str(uuid4())
        track = Track(
            track_id=track_id,
            state=TrackState.TENTATIVE,
            position=reading.position,
            velocity=(0.0, 0.0, 0.0),
            covariance=[[0.0] * 6 for _ in range(6)],
            last_update=reading.timestamp,
            sensor_sources=[reading.sensor_id],
            classification=reading.data.get("classification") if isinstance(reading.data, dict) else None,
            confidence=reading.confidence,
            history=[{"ts": reading.timestamp.isoformat(), "pos": reading.position, "sensor": reading.sensor_id}],
        )
        ekf = EKFFilter()
        ekf.reset(
            [
                float(reading.position[0]),
                float(reading.position[1]),
                float(reading.position[2]),
                0.0,
                0.0,
                0.0,
            ]
        )
        self._tracks[track_id] = track
        self._ctx[track_id] = _TrackContext(updates=1, last_update=reading.timestamp, ekf=ekf)
        return track

    def _update_track(self, track: Track, reading: SensorReading) -> Track:
        if reading.position is None:
            raise ValueError("reading.position is required to update a fused track")
        ctx = self._ctx[track.track_id]
        ctx.ekf.predict()
        ctx.ekf.update([float(reading.position[0]), float(reading.position[1]), float(reading.position[2])])
        updated_state = ctx.ekf.get_state()
        track.position = tuple(float(x) for x in updated_state["position"])
        track.velocity = tuple(float(x) for x in updated_state["velocity"])
        track.covariance = updated_state["covariance"]
        track.last_update = reading.timestamp
        if reading.sensor_id not in track.sensor_sources:
            track.sensor_sources.append(reading.sensor_id)
        if isinstance(reading.data, dict) and reading.data.get("classification"):
            track.classification = str(reading.data["classification"])
        track.confidence = max(0.0, min(1.0, (track.confidence + reading.confidence) / 2))
        track.history.append({"ts": reading.timestamp.isoformat(), "pos": track.position, "sensor": reading.sensor_id})
        if len(track.history) > 200:
            track.history = track.history[-200:]
        ctx.updates += 1
        ctx.last_update = reading.timestamp
        if track.state == TrackState.TENTATIVE and ctx.updates >= 3:
            track.state = TrackState.CONFIRMED
        return track

    def _apply_state_transitions(self) -> None:
        now = datetime.now(timezone.utc)
        for track_id, track in list(self._tracks.items()):
            if track.state == TrackState.DELETED:
                continue
            age = (now - track.last_update).total_seconds()
            if track.state == TrackState.CONFIRMED and age > 10:
                track.state = TrackState.LOST
            if track.state == TrackState.LOST and age > 30:
                track.state = TrackState.DELETED
            if track.state == TrackState.DELETED:
                self._tracks.pop(track_id, None)
                self._ctx.pop(track_id, None)

    def update(self, readings: List[SensorReading]) -> List[Track]:
        """Associate and fuse incoming sensor readings into tactical tracks."""
        if not isinstance(readings, list) or any(not isinstance(r, SensorReading) for r in readings):
            raise ValueError("readings must be a list of SensorReading")
        for reading in readings:
            nearest = self._nearest_track(reading)
            if nearest is None:
                self._create_track(reading)
            else:
                self._update_track(nearest, reading)
        self._apply_state_transitions()
        return list(self._tracks.values())

    def get_tracks(self, state: Optional[TrackState] = None) -> List[Track]:
        if state is not None and not isinstance(state, TrackState):
            raise ValueError("state must be TrackState or None")
        tracks = list(self._tracks.values())
        if state is None:
            return tracks
        return [track for track in tracks if track.state == state]

    def get_track(self, track_id: str) -> Optional[Track]:
        if not isinstance(track_id, str) or not track_id.strip():
            raise ValueError("track_id must be a non-empty string")
        return self._tracks.get(track_id)

    def get_stats(self) -> Dict[str, int]:
        tracks = list(self._tracks.values())
        return {
            "total": len(tracks),
            "confirmed": sum(1 for t in tracks if t.state == TrackState.CONFIRMED),
            "tentative": sum(1 for t in tracks if t.state == TrackState.TENTATIVE),
            "lost": sum(1 for t in tracks if t.state == TrackState.LOST),
        }

    def export_tracks(self) -> List[dict]:
        return [track.to_dict() for track in self._tracks.values()]
