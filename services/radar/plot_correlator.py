"""Scan-to-scan radar plot correlation.

Military context:
Before plots reach the EKF track fuser, they need scan-to-scan association:
grouping detections from consecutive scans that belong to the same physical
target. The Krechet does this internally per radar before feeding the fused
picture. This reduces false tracks and improves initial velocity estimation.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, TypedDict
from uuid import uuid4

from services.radar.models import RadarPlot


class _TrackState(TypedDict):
    last_position: Tuple[float, float, float]
    last_time: datetime
    velocity_estimate: Tuple[float, float, float]
    last_radial_vel: float
    coast_count: int
    updates: int


class PlotCorrelator:
    """Associate radar plots across consecutive scans using nearest-neighbor with velocity gating."""

    def __init__(
        self,
        distance_gate_m: float = 2000.0,
        velocity_gate_mps: float = 100.0,
        max_coast_scans: int = 3,
    ) -> None:
        distance_gate_m = float(distance_gate_m)
        velocity_gate_mps = float(velocity_gate_mps)
        if not math.isfinite(distance_gate_m) or distance_gate_m <= 0.0:
            raise ValueError("distance_gate_m must be a finite value > 0")
        if not math.isfinite(velocity_gate_mps) or velocity_gate_mps < 0.0:
            raise ValueError("velocity_gate_mps must be a finite value >= 0")
        if not isinstance(max_coast_scans, int) or max_coast_scans < 0:
            raise ValueError("max_coast_scans must be a non-negative integer")

        self.distance_gate_m = distance_gate_m
        self.velocity_gate_mps = velocity_gate_mps
        self.max_coast_scans = max_coast_scans
        self._tracks: Dict[str, _TrackState] = {}

    def correlate(self, plots: List[RadarPlot], scan_time: Optional[datetime] = None) -> List[RadarPlot]:
        """Correlate plots from a new scan with existing plot tracks.

        Returns the plots with correlated_track_id filled in.
        New tracks are created for uncorrelated plots.
        """
        if scan_time is None:
            scan_time = datetime.now(timezone.utc)
        elif scan_time.tzinfo is None:
            scan_time = scan_time.replace(tzinfo=timezone.utc)

        assigned_tracks = set()
        updated_tracks = set()
        unassigned_plots: List[RadarPlot] = []

        # Tactical priority: process stronger returns first to lock high-quality custody.
        sorted_plots = sorted(plots, key=lambda p: p.snr_db, reverse=True)

        for plot in sorted_plots:
            if plot.position_cartesian is None:
                unassigned_plots.append(plot)
                continue

            best_track_id = None
            best_distance = float("inf")

            for track_id, track_state in self._tracks.items():
                if track_id in assigned_tracks:
                    continue
                if track_state["coast_count"] > self.max_coast_scans:
                    continue

                last_pos = track_state["last_position"]
                dt = max(0.1, (scan_time - track_state["last_time"]).total_seconds())

                vel = track_state["velocity_estimate"]
                predicted = (
                    last_pos[0] + vel[0] * dt,
                    last_pos[1] + vel[1] * dt,
                    last_pos[2] + vel[2] * dt,
                )

                dist = self._distance(plot.position_cartesian, predicted)
                if dist > self.distance_gate_m:
                    continue

                if plot.radial_velocity_mps != 0.0 and track_state["last_radial_vel"] != 0.0:
                    vel_diff = abs(plot.radial_velocity_mps - track_state["last_radial_vel"])
                    if vel_diff > self.velocity_gate_mps:
                        continue

                if dist < best_distance:
                    best_distance = dist
                    best_track_id = track_id

            if best_track_id is not None:
                plot.correlated_track_id = best_track_id
                assigned_tracks.add(best_track_id)
                updated_tracks.add(best_track_id)

                prev = self._tracks[best_track_id]
                dt = max(0.1, (scan_time - prev["last_time"]).total_seconds())
                vel_est = (
                    (plot.position_cartesian[0] - prev["last_position"][0]) / dt,
                    (plot.position_cartesian[1] - prev["last_position"][1]) / dt,
                    (plot.position_cartesian[2] - prev["last_position"][2]) / dt,
                )
                prev["last_position"] = plot.position_cartesian
                prev["last_time"] = scan_time
                prev["velocity_estimate"] = vel_est
                prev["last_radial_vel"] = plot.radial_velocity_mps
                prev["coast_count"] = 0
                prev["updates"] += 1
            else:
                unassigned_plots.append(plot)

        for plot in unassigned_plots:
            if plot.position_cartesian is None:
                continue
            new_id = f"rtrk-{uuid4().hex[:8]}"
            plot.correlated_track_id = new_id
            self._tracks[new_id] = _TrackState(
                last_position=plot.position_cartesian,
                last_time=scan_time,
                velocity_estimate=(0.0, 0.0, 0.0),
                last_radial_vel=plot.radial_velocity_mps,
                coast_count=0,
                updates=1,
            )
            updated_tracks.add(new_id)

        for track_id, state in list(self._tracks.items()):
            if track_id in updated_tracks:
                continue
            state["coast_count"] += 1

        dead = [tid for tid, s in self._tracks.items() if s["coast_count"] > self.max_coast_scans + 2]
        for tid in dead:
            del self._tracks[tid]

        return plots

    @staticmethod
    def _distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    def get_active_track_count(self) -> int:
        return sum(1 for s in self._tracks.values() if s["coast_count"] <= self.max_coast_scans)

    def get_stats(self) -> Dict[str, int]:
        return {
            "active_tracks": self.get_active_track_count(),
            "total_tracks": len(self._tracks),
            "coasting": sum(1 for s in self._tracks.values() if 0 < s["coast_count"] <= self.max_coast_scans),
        }
