"""Adapter for Western AESA tactical surveillance radars.

Military context:
This adapter models AN/TPS-80, Giraffe, and TRML-4D style feeds to support
coalition interoperability while preserving sovereign offline fusion pipelines.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter


class WesternAESAAdapter(Generic3DRadarAdapter):
    """Normalize Western AESA style payloads to RadarScan."""

    def parse_raw_scan(self, raw_scan: Dict[str, Any]):
        if not isinstance(raw_scan, dict):
            raise ValueError("raw_scan must be a dictionary")
        detections = raw_scan.get("detections", raw_scan.get("plots", []))
        if not isinstance(detections, list):
            raise ValueError("Western AESA detections must be a list")

        normalized_plots: List[Dict[str, Any]] = []
        for idx, det in enumerate(detections):
            if not isinstance(det, dict):
                raise ValueError(f"detection {idx} must be a dictionary")
            normalized_plots.append(
                {
                    "plot_id": det.get("plot_id", det.get("contact_id", f"aesa-{idx}")),
                    "range_m": float(det.get("range_m", float(det.get("range_nm", 0.0)) * 1852.0)),
                    "azimuth_deg": float(det.get("azimuth_deg", det.get("az_deg", 0.0))),
                    "elevation_deg": float(det.get("elevation_deg", det.get("el_deg", 0.0))),
                    "radial_velocity_mps": float(det.get("radial_velocity_mps", det.get("closure_rate_mps", 0.0))),
                    "rcs_m2": float(det.get("rcs_m2", 10.0 ** (float(det.get("rcs_dbsm", -12.0)) / 10.0))),
                    "snr_db": float(det.get("snr_db", det.get("signal_quality_db", 18.0))),
                    "confidence": float(det.get("confidence", det.get("track_quality", 0.98))),
                    "metadata": {
                        "source_format": "western_aesa",
                        "iff_status": det.get("iff_status", "unknown"),
                        "scan_cell": det.get("scan_cell", "default"),
                    },
                }
            )

        wrapped = {
            "scan_id": raw_scan.get("scan_id", raw_scan.get("burst_id", "")),
            "scan_index": raw_scan.get("scan_index", raw_scan.get("burst_index", 0)),
            "scan_mode": raw_scan.get("scan_mode", "VOLUME"),
            "timestamp": raw_scan.get("timestamp"),
            "plots": normalized_plots,
        }
        return super().parse_raw_scan(wrapped)
