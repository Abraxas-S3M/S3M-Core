"""Scan-to-scan radar plot correlation utilities.

Military context:
This JPDA-lite correlator links detections across consecutive sweeps so command
nodes receive stable contact continuity before deeper EKF track maintenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import cos, radians, sin, sqrt
from typing import Dict, List, Optional, Set

from services.radar.models import PlotCorrelation, RadarPlot, RadarScan


def _polar_to_local_xyz(plot: RadarPlot) -> tuple[float, float, float]:
    horizontal = plot.range_m * cos(radians(plot.elevation_deg))
    x = horizontal * sin(radians(plot.azimuth_deg))
    y = horizontal * cos(radians(plot.azimuth_deg))
    z = plot.range_m * sin(radians(plot.elevation_deg))
    return (x, y, z)


def _distance_m(a: RadarPlot, b: RadarPlot) -> float:
    ax, ay, az = _polar_to_local_xyz(a)
    bx, by, bz = _polar_to_local_xyz(b)
    return sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


@dataclass
class PlotCorrelator:
    """Nearest-neighbor correlator with speed/velocity gating."""

    max_speed_mps: float = 450.0
    max_velocity_delta_mps: float = 120.0
    base_distance_gate_m: float = 250.0
    _last_scan_by_radar: Dict[str, RadarScan] = field(default_factory=dict)

    def correlate(self, scan: RadarScan) -> List[PlotCorrelation]:
        if not isinstance(scan, RadarScan):
            raise ValueError("scan must be RadarScan")
        previous_scan = self._last_scan_by_radar.get(scan.radar_id)
        self._last_scan_by_radar[scan.radar_id] = scan
        if previous_scan is None or not previous_scan.plots or not scan.plots:
            return []
        dt_seconds = (scan.timestamp - previous_scan.timestamp).total_seconds()
        if dt_seconds <= 0.0:
            dt_seconds = 1.0 / 10.0
        return self._associate(previous_scan=previous_scan, current_scan=scan, dt_seconds=dt_seconds)

    def _associate(self, previous_scan: RadarScan, current_scan: RadarScan, dt_seconds: float) -> List[PlotCorrelation]:
        correlations: List[PlotCorrelation] = []
        matched_previous: Set[str] = set()
        dynamic_gate = self.base_distance_gate_m + self.max_speed_mps * dt_seconds

        for current_plot in current_scan.plots:
            candidate: Optional[RadarPlot] = None
            best_distance = float("inf")
            for previous_plot in previous_scan.plots:
                if previous_plot.plot_id in matched_previous:
                    continue
                velocity_delta = abs(current_plot.radial_velocity_mps - previous_plot.radial_velocity_mps)
                if velocity_delta > self.max_velocity_delta_mps:
                    continue
                distance = _distance_m(previous_plot, current_plot)
                if distance > dynamic_gate:
                    continue
                if distance < best_distance:
                    best_distance = distance
                    candidate = previous_plot
            if candidate is None:
                continue
            matched_previous.add(candidate.plot_id)
            velocity_delta = abs(current_plot.radial_velocity_mps - candidate.radial_velocity_mps)
            score = self._score(distance_m=best_distance, dynamic_gate_m=dynamic_gate, velocity_delta_mps=velocity_delta)
            correlations.append(
                PlotCorrelation(
                    radar_id=current_scan.radar_id,
                    previous_plot_id=candidate.plot_id,
                    current_plot_id=current_plot.plot_id,
                    dt_seconds=dt_seconds,
                    spatial_distance_m=best_distance,
                    radial_velocity_delta_mps=velocity_delta,
                    score=score,
                )
            )
        return correlations

    @staticmethod
    def _score(distance_m: float, dynamic_gate_m: float, velocity_delta_mps: float) -> float:
        if dynamic_gate_m <= 0.0:
            return 0.0
        distance_component = max(0.0, 1.0 - (distance_m / dynamic_gate_m))
        velocity_component = 1.0 / (1.0 + velocity_delta_mps / 20.0)
        return max(0.0, min(1.0, 0.7 * distance_component + 0.3 * velocity_component))

    def clear(self, radar_id: Optional[str] = None) -> None:
        if radar_id is None:
            self._last_scan_by_radar.clear()
            return
        self._last_scan_by_radar.pop(radar_id, None)

    def has_history(self, radar_id: str) -> bool:
        return radar_id in self._last_scan_by_radar
