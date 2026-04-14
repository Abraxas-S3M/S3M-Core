"""Adapter for RPS-202 class vehicle-mounted 3D radar.

Military context:
Vehicle-integrated RPS-202-like radars provide higher-fidelity 3D surveillance
for battalion-level air defense and cueing to medium-range effectors.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter


class RPS202Adapter(Generic3DRadarAdapter):
    """Normalize RPS-202 style payloads to RadarScan."""

    def parse_raw_scan(self, raw_scan: Dict[str, Any]):
        if not isinstance(raw_scan, dict):
            raise ValueError("raw_scan must be a dictionary")
        detections = raw_scan.get("tracks", raw_scan.get("detections", raw_scan.get("plots", [])))
        if not isinstance(detections, list):
            raise ValueError("RPS-202 detections must be a list")

        normalized_plots: List[Dict[str, Any]] = []
        for idx, det in enumerate(detections):
            if not isinstance(det, dict):
                raise ValueError(f"detection {idx} must be a dictionary")
            normalized_plots.append(
                {
                    "plot_id": det.get("plot_id", det.get("track_id", f"rps202-{idx}")),
                    "range_m": float(det.get("range_m", float(det.get("range_km", 0.0)) * 1000.0)),
                    "azimuth_deg": float(det.get("azimuth_deg", det.get("bearing_deg", 0.0))),
                    "elevation_deg": float(det.get("elevation_deg", det.get("el_deg", 0.0))),
                    "radial_velocity_mps": float(det.get("radial_velocity_mps", det.get("doppler_mps", 0.0))),
                    "rcs_m2": float(det.get("rcs_m2", 10.0 ** (float(det.get("rcs_dbsm", -15.0)) / 10.0))),
                    "snr_db": float(det.get("snr_db", 15.0)),
                    "confidence": float(det.get("confidence", det.get("track_confidence", 0.97))),
                    "metadata": {
                        "source_format": "rps202",
                        "quality_index": det.get("quality_index", 0.8),
                        "track_state": det.get("state", "TRACK"),
                    },
                }
            )

        wrapped = {
            "scan_id": raw_scan.get("scan_id", raw_scan.get("volume_id", "")),
            "scan_index": raw_scan.get("scan_index", raw_scan.get("volume_index", 0)),
            "scan_mode": raw_scan.get("scan_mode", "TRACK_WHILE_SCAN"),
            "timestamp": raw_scan.get("timestamp"),
            "plots": normalized_plots,
        }
        return super().parse_raw_scan(wrapped)
