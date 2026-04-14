"""Adapter for generic 3D radar feeds with elevation support.

Military context:
3D surveillance radars provide volumetric contacts needed for layered
engagement geometry and altitude-based effector assignment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarPlot, RadarScan, ScanMode


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _coerce_rcs_m2(entry: Dict[str, Any]) -> float:
    if "rcs_m2" in entry:
        return max(0.0, float(entry["rcs_m2"]))
    if "rcs_dbsm" in entry:
        return max(0.0, 10.0 ** (float(entry["rcs_dbsm"]) / 10.0))
    return 0.1


class Generic3DRadarAdapter(BaseRadarAdapter):
    """Normalize generic 3D radar payloads to typed RadarScan."""

    def parse_raw_scan(self, raw_scan: Dict[str, Any]) -> RadarScan:
        if not isinstance(raw_scan, dict):
            raise ValueError("raw_scan must be a dictionary")
        scan_mode = ScanMode.from_value(raw_scan.get("scan_mode", "VOLUME"))
        timestamp = _to_datetime(raw_scan.get("timestamp"))
        scan_index = int(raw_scan.get("scan_index", 0))
        scan_id = str(raw_scan.get("scan_id") or f"{self.config.radar_id}-{scan_index}")
        plots_raw = raw_scan.get("plots", [])
        if not isinstance(plots_raw, list):
            raise ValueError("raw_scan['plots'] must be a list")

        plots: List[RadarPlot] = []
        for idx, entry in enumerate(plots_raw):
            if not isinstance(entry, dict):
                raise ValueError(f"plot {idx} must be a dictionary")
            range_m = float(entry.get("range_m", float(entry.get("range_km", 0.0)) * 1000.0))
            azimuth_deg = float(entry.get("azimuth_deg", entry.get("az_deg", 0.0)))
            elevation_deg = float(entry.get("elevation_deg", entry.get("el_deg", 0.0)))
            radial_velocity = float(entry.get("radial_velocity_mps", entry.get("vr_mps", 0.0)))
            snr_db = float(entry.get("snr_db", 14.0))
            plot = RadarPlot(
                plot_id=str(entry.get("plot_id", f"{scan_id}-plot-{idx}")),
                timestamp=_to_datetime(entry.get("timestamp", timestamp)),
                range_m=range_m,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
                radial_velocity_mps=radial_velocity,
                rcs_m2=_coerce_rcs_m2(entry),
                snr_db=snr_db,
                confidence=float(entry.get("confidence", 1.0)),
                metadata=dict(entry.get("metadata", {})),
            )
            plots.append(plot)

        return RadarScan(
            radar_id=self.config.radar_id,
            scan_mode=scan_mode,
            timestamp=timestamp,
            scan_id=scan_id,
            scan_index=scan_index,
            plots=plots,
        )
