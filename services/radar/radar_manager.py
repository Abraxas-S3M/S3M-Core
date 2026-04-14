"""In-memory radar manager for tactical sensor orchestration.

Military context:
The manager maintains a deterministic local radar picture suitable for
offline command-post simulation on edge compute hardware.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
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


def _parse_xyz(raw_position: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw_position, (list, tuple)) or len(raw_position) != 3:
        raise ValueError(f"{field_name} must be [x_m, y_m, z_m]")
    try:
        return (float(raw_position[0]), float(raw_position[1]), float(raw_position[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain numeric coordinates") from exc


class RadarManager:
    """Coordinate radar registration, scan ingest, and simple track fusion."""

    def __init__(self) -> None:
        self._radars: Dict[str, RadarUnit] = {}
        self._status: Dict[str, RadarStatus] = {}
        self._plots_by_radar: Dict[str, List[RadarPlot]] = {}
        self._tracks: Dict[str, FusedTrack] = {}

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
            classification = RCSClassification.UNKNOWN
            for candidate in RCSClassification:
                if candidate.value == classification_text:
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
                    rcs_classification=classification,
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
                    self._tracks[track_id] = FusedTrack(
                        track_id=track_id,
                        state=TrackState.TENTATIVE,
                        last_update=now,
                        source_hits=1,
                    )
                    continue

                existing.source_hits += 1
                existing.last_update = now
                if existing.source_hits >= 2:
                    existing.state = TrackState.CONFIRMED
        return list(self._tracks.values())

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

