"""Scan-to-scan radar plot correlation for tactical continuity."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from services.radar.models import RadarPlot


@dataclass
class _CorrelatedTrack:
    track_id: str
    position: Tuple[float, float, float]
    missed_scans: int = 0


class PlotCorrelator:
    """Associate plots across scans to maintain tactical track IDs."""

    def __init__(self, gate_distance_m: float = 150.0, max_missed_scans: int = 5) -> None:
        if not isinstance(gate_distance_m, (int, float)) or float(gate_distance_m) <= 0:
            raise ValueError("gate_distance_m must be positive")
        if not isinstance(max_missed_scans, int) or max_missed_scans < 0:
            raise ValueError("max_missed_scans must be a non-negative integer")
        self._gate_distance_m = float(gate_distance_m)
        self._max_missed_scans = max_missed_scans
        self._tracks: Dict[str, _CorrelatedTrack] = {}
        self._next_track_id = 1

    def correlate(self, plots: List[RadarPlot]) -> List[RadarPlot]:
        if not isinstance(plots, list):
            raise ValueError("plots must be a list")

        unmatched_tracks = set(self._tracks.keys())
        for plot in plots:
            if not isinstance(plot, RadarPlot) or plot.position_cartesian is None:
                continue

            best_track = self._find_best_track(plot.position_cartesian, unmatched_tracks)
            if best_track is None:
                track_id = self._new_track_id()
                self._tracks[track_id] = _CorrelatedTrack(track_id=track_id, position=plot.position_cartesian)
                plot.correlated_track_id = track_id
            else:
                correlated = self._tracks[best_track]
                correlated.position = plot.position_cartesian
                correlated.missed_scans = 0
                plot.correlated_track_id = best_track
                unmatched_tracks.discard(best_track)

        for track_id in list(unmatched_tracks):
            track = self._tracks.get(track_id)
            if track is None:
                continue
            track.missed_scans += 1
            if track.missed_scans > self._max_missed_scans:
                del self._tracks[track_id]

        return plots

    def get_active_track_count(self) -> int:
        return len(self._tracks)

    def _find_best_track(self, position: Tuple[float, float, float], candidates: set[str]) -> str | None:
        best_track_id: str | None = None
        best_distance = self._gate_distance_m
        for track_id in candidates:
            track = self._tracks[track_id]
            distance = self._distance(position, track.position)
            if distance <= best_distance:
                best_distance = distance
                best_track_id = track_id
        return best_track_id

    def _new_track_id(self) -> str:
        track_id = f"trk-{self._next_track_id:06d}"
        self._next_track_id += 1
        return track_id

    def _distance(self, p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        dz = p1[2] - p2[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

