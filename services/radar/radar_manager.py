"""In-memory radar manager for tactical sensor orchestration.

Military context:
The manager maintains a deterministic local radar picture suitable for
offline command-post simulation on edge compute hardware.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, List, Optional, Protocol, Tuple
from uuid import uuid4

from services.radar.models import (
    FusedTrack,
    RCSClassification,
    RadarConfig,
    RadarPlot,
    RadarStatus,
    RadarUnit,
    TrackState,
)


class AirDefenseAllocator(Protocol):
    """Protocol for optional tactical target allocation integration."""

    def allocate(
        self,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_speed_mps: float,
        target_classification: str,
    ) -> Any:
        ...


class InterceptorGuidanceManager(Protocol):
    """Protocol for optional interceptor midcourse guidance integration."""

    def get_active_interceptions(self) -> List[Dict[str, Any]]:
        ...

    def guide(
        self,
        interceptor_id: str,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
    ) -> Any:
        ...


class PredictiveDefenseManagerLike(Protocol):
    """Protocol for optional predictive-defense integration."""

    def process_tracks(self, tracks: List[FusedTrack]) -> Any:
        ...


ALLOCATABLE_TRACK_CLASSES = frozenset(
    {"ENEMY_UAV", "ENEMY_CRUISE_MISSILE", "ENEMY_HELICOPTER", "ENEMY_AIRCRAFT"}
)


def _parse_xyz(raw_position: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw_position, (list, tuple)) or len(raw_position) != 3:
        raise ValueError(f"{field_name} must be [x_m, y_m, z_m]")
    try:
        return (float(raw_position[0]), float(raw_position[1]), float(raw_position[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain numeric coordinates") from exc


def _parse_optional_xyz(raw_position: Any) -> Optional[Tuple[float, float, float]]:
    if raw_position is None:
        return None
    if not isinstance(raw_position, (list, tuple)) or len(raw_position) != 3:
        return None
    try:
        return (float(raw_position[0]), float(raw_position[1]), float(raw_position[2]))
    except (TypeError, ValueError):
        return None


class RadarManager:
    """Coordinate radar registration, scan ingest, and simple track fusion."""

    def __init__(
        self,
        air_defense_allocator: Optional[AirDefenseAllocator] = None,
        interceptor_manager: Optional[InterceptorGuidanceManager] = None,
        predictive_defense_manager: Optional[PredictiveDefenseManagerLike] = None,
    ) -> None:
        self._radars: Dict[str, RadarUnit] = {}
        self._status: Dict[str, RadarStatus] = {}
        self._plots_by_radar: Dict[str, List[RadarPlot]] = {}
        self._tracks: Dict[str, FusedTrack] = {}
        self._air_defense_allocator = air_defense_allocator
        self._interceptor_manager = interceptor_manager
        self._predictive_defense_manager = predictive_defense_manager
        self._allocated_track_ids: set[str] = set()

    def list_radars(self) -> List[RadarUnit]:
        return list(self._radars.values())

    def get_radar(self, radar_id: str) -> Optional[RadarUnit]:
        return self._radars.get(str(radar_id))

    def register_radar(self, config: RadarConfig) -> RadarUnit:
        radar_id = str(uuid4())
        unit = RadarUnit(radar_id=radar_id, config=config)
        self._radars[radar_id] = unit
        self._status[radar_id] = RadarStatus(radar_id=radar_id)
        self._plots_by_radar.setdefault(radar_id, [])
        return unit

    def get_status(self, radar_id: str) -> Optional[RadarStatus]:
        return self._status.get(str(radar_id))

    def list_tracks(self) -> List[FusedTrack]:
        return list(self._tracks.values())

    def get_all_status(self) -> Dict[str, Any]:
        statuses = [status.to_dict() for status in self._status.values()]
        return {"radars": statuses, "count": len(statuses)}

    def ingest_scan(self, radar_id: str, payload: Dict[str, Any]) -> List[RadarPlot]:
        radar_key = str(radar_id)
        if radar_key not in self._radars:
            raise ValueError("Radar not found")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        raw_plots = payload.get("plots")
        if not isinstance(raw_plots, list):
            raise ValueError("plots must be a list")

        now = datetime.now(timezone.utc)
        produced_plots: List[RadarPlot] = []
        correlated_hits = 0
        for idx, raw_plot in enumerate(raw_plots):
            if not isinstance(raw_plot, dict):
                raise ValueError(f"plot[{idx}] must be an object")
            position = _parse_xyz(raw_plot.get("position", [0.0, 0.0, 0.0]), field_name=f"plot[{idx}].position")
            classification_text = str(raw_plot.get("rcs_classification", "unknown")).strip().lower()
            classification_key = {
                "small": "small_uav",
                "medium": "medium_uav",
                "large": "large_uav",
                "fighter_aircraft": "fighter",
                "fighter_jet": "fighter",
            }.get(classification_text, classification_text)
            classification = RCSClassification.UNKNOWN
            for candidate in RCSClassification:
                if candidate.value == classification_key:
                    classification = candidate
                    break
            track_id_raw = raw_plot.get("track_id") or raw_plot.get("correlated_track_id")
            track_id = str(track_id_raw) if track_id_raw else None
            if track_id:
                correlated_hits += 1

            produced_plots.append(
                RadarPlot(
                    plot_id=str(uuid4()),
                    radar_id=radar_key,
                    position=position,
                    rcs_classification=classification.value,
                    correlated_track_id=track_id,
                    timestamp=now,
                    attributes={k: v for k, v in raw_plot.items() if k not in {"position", "track_id", "correlated_track_id", "rcs_classification"}},
                )
            )

        self._plots_by_radar.setdefault(radar_key, []).extend(produced_plots)
        status = self._status[radar_key]
        status.scans_received += 1
        status.plots_received += len(produced_plots)
        status.plots_correlated += correlated_hits
        status.last_scan_time = now
        return produced_plots

    def process_fused_tracks(self) -> List[FusedTrack]:
        now = datetime.now(timezone.utc)
        for plots in self._plots_by_radar.values():
            for plot in plots:
                if not plot.correlated_track_id:
                    continue
                track_id = str(plot.correlated_track_id)
                existing = self._tracks.get(track_id)
                if existing is None:
                    track_classification = self._derive_track_classification(plot)
                    self._tracks[track_id] = FusedTrack(
                        track_id=track_id,
                        state=TrackState.TENTATIVE,
                        last_update=now,
                        source_hits=1,
                        classification=track_classification,
                        position=plot.position or (0.0, 0.0, 0.0),
                        sensor_sources=[plot.radar_id],
                    )
                    continue

                existing.source_hits += 1
                existing.last_update = now
                if plot.position:
                    existing.position = plot.position
                if plot.radar_id and plot.radar_id not in existing.sensor_sources:
                    existing.sensor_sources.append(plot.radar_id)
                track_classification = self._derive_track_classification(plot)
                if track_classification != "UNKNOWN":
                    existing.classification = track_classification
                if existing.source_hits >= 2:
                    existing.state = TrackState.CONFIRMED
        confirmed_tracks = [track for track in self._tracks.values() if track.state is TrackState.CONFIRMED]
        self._allocate_confirmed_tracks()
        self._process_predictive_defense(confirmed_tracks)
        self._guide_active_interceptions()
        return list(self._tracks.values())

    def _process_predictive_defense(self, confirmed_tracks: List[FusedTrack]) -> None:
        if self._predictive_defense_manager is None:
            return
        try:
            # Tactical context: confirmed fused tracks cue predictive-defense
            # pre-positioning while preserving radar fusion continuity.
            self._predictive_defense_manager.process_tracks(confirmed_tracks)
        except Exception:
            # Tactical resilience: predictive-defense faults must not block
            # radar fusion outputs needed by other engagement loops.
            return

    def _derive_track_classification(self, plot: RadarPlot) -> str:
        attr_classification = (
            plot.attributes.get("target_allocator_classification")
            or plot.attributes.get("classification")
        )
        if isinstance(attr_classification, str) and attr_classification.strip():
            return attr_classification.strip().upper()

        mapping = {
            RCSClassification.SMALL_UAV: "ENEMY_UAV",
            RCSClassification.MEDIUM_UAV: "ENEMY_UAV",
            RCSClassification.LARGE_UAV: "ENEMY_UAV",
            RCSClassification.CRUISE_MISSILE: "ENEMY_CRUISE_MISSILE",
            RCSClassification.HELICOPTER: "ENEMY_HELICOPTER",
            RCSClassification.FIGHTER: "ENEMY_AIRCRAFT",
            RCSClassification.FIGHTER_AIRCRAFT: "ENEMY_AIRCRAFT",
            RCSClassification.LARGE_AIRCRAFT: "ENEMY_AIRCRAFT",
        }
        return mapping.get(plot.rcs_classification, "UNKNOWN")

    def _track_speed_mps(self, track: FusedTrack) -> float:
        vx, vy, vz = track.velocity
        return float(sqrt((vx * vx) + (vy * vy) + (vz * vz)))

    def _allocate_confirmed_tracks(self) -> None:
        if self._air_defense_allocator is None:
            return
        for track in self._tracks.values():
            if track.state is not TrackState.CONFIRMED:
                continue
            classification = str(track.classification or "UNKNOWN").upper()
            if classification not in ALLOCATABLE_TRACK_CLASSES:
                continue
            if track.track_id in self._allocated_track_ids:
                continue
            # Tactical context: each confirmed hostile air track should trigger one
            # deterministic effector allocation attempt to prevent duplicate fires.
            self._air_defense_allocator.allocate(
                target_id=track.track_id,
                target_position=track.position,
                target_speed_mps=self._track_speed_mps(track),
                target_classification=classification,
            )
            self._allocated_track_ids.add(track.track_id)

    def _guide_active_interceptions(self) -> None:
        if self._interceptor_manager is None:
            return
        active_interceptions = self._interceptor_manager.get_active_interceptions()
        if not active_interceptions:
            return

        interceptor_ids_by_target: Dict[str, List[str]] = {}
        for interception in active_interceptions:
            target_id = str(interception.get("target_id", "")).strip()
            interceptor_id = str(interception.get("interceptor_id", "")).strip()
            if not target_id or not interceptor_id:
                continue
            interceptor_ids_by_target.setdefault(target_id, []).append(interceptor_id)
        if not interceptor_ids_by_target:
            return

        for track in self._tracks.values():
            if track.state is not TrackState.CONFIRMED:
                continue
            interceptor_ids = interceptor_ids_by_target.get(track.track_id)
            if not interceptor_ids:
                continue
            # Tactical context: fused tracks drive each midcourse update so
            # interceptor drones stay synchronized with the latest radar picture.
            interceptor_pos = _parse_optional_xyz(track.metadata.get("interceptor_pos")) or (0.0, 0.0, 0.0)
            interceptor_vel = _parse_optional_xyz(track.metadata.get("interceptor_vel")) or (0.0, 0.0, 0.0)
            for interceptor_id in interceptor_ids:
                try:
                    self._interceptor_manager.guide(
                        interceptor_id=interceptor_id,
                        interceptor_pos=interceptor_pos,
                        interceptor_vel=interceptor_vel,
                        target_pos=track.position,
                        target_vel=track.velocity,
                    )
                except Exception:
                    # Tactical resilience: one guidance fault must not block fusion
                    # updates for the rest of the air picture.
                    continue

    def get_stats(self) -> Dict[str, Any]:
        scans_received = sum(status.scans_received for status in self._status.values())
        plots_received = sum(status.plots_received for status in self._status.values())
        plots_correlated = sum(status.plots_correlated for status in self._status.values())
        return {
            "radars_registered": len(self._radars),
            "scans_received": scans_received,
            "plots_received": plots_received,
            "plots_correlated": plots_correlated,
            "tracks": len(self._tracks),
        }

