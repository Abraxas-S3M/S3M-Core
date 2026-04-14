"""Radar manager for ingesting scans and producing fused tracks.

Military context:
Implements edge-local radar fusion that combines detections from layered sensors
to preserve continuity of hostile air tracks as they penetrate defended airspace.
"""

from __future__ import annotations

from collections import Counter
from math import cos, radians, sin
from typing import Any

from services.radar.models import (
    FusedTrack,
    RCSClassification,
    RadarConfig,
    RadarPlot,
    TrackState,
)


class RadarManager:
    """Manage tactical radar registrations, scan ingest, and local track fusion."""

    def __init__(self) -> None:
        self._radars: dict[str, RadarConfig] = {}
        self._plots_by_radar: dict[str, list[RadarPlot]] = {}
        self._status: dict[str, dict[str, int]] = {}
        self._pending_plots: list[RadarPlot] = []

    def register_radar(self, config: RadarConfig, *, replace_existing: bool = False) -> None:
        if config.radar_id in self._radars and not replace_existing:
            raise ValueError(f"Radar {config.radar_id} already registered")
        self._radars[config.radar_id] = config
        self._plots_by_radar.setdefault(config.radar_id, [])
        self._status.setdefault(config.radar_id, {"scans": 0, "plots": 0, "correlated": 0})

    def get_radar(self, radar_id: str) -> RadarConfig | None:
        return self._radars.get(radar_id)

    def get_all_status(self) -> dict[str, dict[str, int]]:
        return {rid: dict(stats) for rid, stats in self._status.items()}

    def ingest_scan(self, radar_id: str, payload: dict[str, Any]) -> list[RadarPlot]:
        radar = self._radars.get(radar_id)
        if radar is None:
            raise ValueError(f"Unknown radar_id: {radar_id}")
        plots_payload = payload.get("plots")
        if not isinstance(plots_payload, list):
            raise ValueError("payload must include a list under key 'plots'")

        self._status[radar_id]["scans"] += 1
        accepted: list[RadarPlot] = []
        for raw_plot in plots_payload:
            if not isinstance(raw_plot, dict):
                continue
            range_m = float(raw_plot.get("range_m", -1.0))
            if range_m < 0.0 or range_m > radar.max_range_m:
                continue
            azimuth = float(raw_plot.get("azimuth_deg", 0.0))
            elevation = float(raw_plot.get("elevation_deg", 0.0))
            velocity = float(raw_plot.get("velocity_mps", 0.0))
            rcs_dbsm = float(raw_plot.get("rcs_dbsm", -30.0))
            snr_db = float(raw_plot.get("snr_db", 0.0))
            position = self._to_cartesian(
                radar_position=radar.position,
                range_m=range_m,
                azimuth_deg=azimuth,
                elevation_deg=elevation,
            )
            rcs_classification, confidence = self._classify_rcs(rcs_dbsm=rcs_dbsm)
            plot = RadarPlot(
                radar_id=radar_id,
                range_m=range_m,
                azimuth_deg=azimuth,
                elevation_deg=elevation,
                velocity_mps=velocity,
                rcs_dbsm=rcs_dbsm,
                snr_db=snr_db,
                position_cartesian=position,
                rcs_classification=rcs_classification,
                classification_confidence=confidence,
            )
            accepted.append(plot)
            self._plots_by_radar[radar_id].append(plot)
            self._pending_plots.append(plot)

        self._status[radar_id]["plots"] += len(accepted)
        return accepted

    def process_fused_tracks(self) -> list[FusedTrack]:
        if not self._pending_plots:
            return []

        grouped: list[list[RadarPlot]] = []
        for plot in self._pending_plots:
            placed = False
            for group in grouped:
                if self._is_same_track(plot, group):
                    group.append(plot)
                    placed = True
                    break
            if not placed:
                grouped.append([plot])

        tracks: list[FusedTrack] = []
        for group_plots in grouped:
            if not group_plots:
                continue
            sensors = sorted({plot.radar_id for plot in group_plots})
            avg_position = (
                sum(plot.position_cartesian[0] for plot in group_plots) / len(group_plots),
                sum(plot.position_cartesian[1] for plot in group_plots) / len(group_plots),
                sum(plot.position_cartesian[2] for plot in group_plots) / len(group_plots),
            )
            mean_velocity = sum(plot.velocity_mps for plot in group_plots) / len(group_plots)
            avg_az = sum(plot.azimuth_deg for plot in group_plots) / len(group_plots)
            avg_el = sum(plot.elevation_deg for plot in group_plots) / len(group_plots)
            velocity_vector = self._to_velocity_vector(
                speed_mps=mean_velocity,
                azimuth_deg=avg_az,
                elevation_deg=avg_el,
            )
            classification_counts = Counter(plot.rcs_classification for plot in group_plots)
            dominant_class = classification_counts.most_common(1)[0][0]

            # Tactical note: multi-radar corroboration upgrades a target from
            # tentative to confirmed for downstream weapon-assignment logic.
            state = TrackState.CONFIRMED if len(sensors) > 1 else TrackState.TENTATIVE
            if state is TrackState.CONFIRMED:
                for sensor_id in sensors:
                    self._status[sensor_id]["correlated"] += 1

            tracks.append(
                FusedTrack(
                    position=avg_position,
                    velocity=velocity_vector,
                    sensor_sources=sensors,
                    classification=dominant_class.value,
                    state=state,
                )
            )

        self._pending_plots = []
        return tracks

    @staticmethod
    def _is_same_track(candidate: RadarPlot, group: list[RadarPlot]) -> bool:
        if not group:
            return True
        lead = group[0]
        if candidate.rcs_classification is not lead.rcs_classification:
            return False
        mean_az = sum(plot.azimuth_deg for plot in group) / len(group)
        mean_el = sum(plot.elevation_deg for plot in group) / len(group)
        mean_velocity = sum(plot.velocity_mps for plot in group) / len(group)
        # Tactical note: permissive angular gates preserve a single track while a
        # low-RCS target closes rapidly through layered radar rings.
        return (
            abs(candidate.azimuth_deg - mean_az) <= 6.0
            and abs(candidate.elevation_deg - mean_el) <= 4.0
            and abs(candidate.velocity_mps - mean_velocity) <= 20.0
        )

    @staticmethod
    def _classify_rcs(*, rcs_dbsm: float) -> tuple[RCSClassification, float]:
        if rcs_dbsm <= -15.0:
            return (RCSClassification.MICRO_UAV, 0.88)
        if rcs_dbsm <= -8.0:
            return (RCSClassification.SHAHED_CLASS_UAV, 0.83)
        if rcs_dbsm <= -3.0:
            return (RCSClassification.TACTICAL_UAV, 0.78)
        if rcs_dbsm <= 8.0:
            return (RCSClassification.CRUISE_MISSILE, 0.7)
        return (RCSClassification.AIRCRAFT, 0.67)

    @staticmethod
    def _to_cartesian(
        *,
        radar_position: tuple[float, float, float],
        range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
    ) -> tuple[float, float, float]:
        azimuth_rad = radians(azimuth_deg)
        elevation_rad = radians(elevation_deg)
        horizontal_range = range_m * cos(elevation_rad)
        x = radar_position[0] + horizontal_range * cos(azimuth_rad)
        y = radar_position[1] + horizontal_range * sin(azimuth_rad)
        z = radar_position[2] + range_m * sin(elevation_rad)
        return (x, y, z)

    @staticmethod
    def _to_velocity_vector(
        *,
        speed_mps: float,
        azimuth_deg: float,
        elevation_deg: float,
    ) -> tuple[float, float, float]:
        azimuth_rad = radians(azimuth_deg)
        elevation_rad = radians(elevation_deg)
        horizontal_speed = speed_mps * cos(elevation_rad)
        vx = horizontal_speed * cos(azimuth_rad)
        vy = horizontal_speed * sin(azimuth_rad)
        vz = speed_mps * sin(elevation_rad)
        return (vx, vy, vz)
