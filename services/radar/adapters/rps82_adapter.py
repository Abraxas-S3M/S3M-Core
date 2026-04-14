"""Adapter for RPS-82 class portable tactical radar.

Military context:
Portable RPS-82-like sensors are frequently deployed for point defense and
forward units, so this parser tolerates compact field telemetry formats.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.radar.adapters.generic_2d_radar import Generic2DRadarAdapter


class RPS82Adapter(Generic2DRadarAdapter):
    """Normalize RPS-82 style payloads to RadarScan."""

    def parse_raw_scan(self, raw_scan: Dict[str, Any]):
        if not isinstance(raw_scan, dict):
            raise ValueError("raw_scan must be a dictionary")
        contacts = raw_scan.get("contacts", raw_scan.get("plots", []))
        if not isinstance(contacts, list):
            raise ValueError("RPS-82 contacts must be a list")
        normalized_plots: List[Dict[str, Any]] = []
        for idx, contact in enumerate(contacts):
            if not isinstance(contact, dict):
                raise ValueError(f"contact {idx} must be a dictionary")
            normalized_plots.append(
                {
                    "plot_id": contact.get("plot_id", contact.get("id", f"rps82-{idx}")),
                    "range_m": float(contact.get("range_m", float(contact.get("range_km", 0.0)) * 1000.0)),
                    "azimuth_deg": float(contact.get("azimuth_deg", contact.get("az_deg", 0.0))),
                    "radial_velocity_mps": float(contact.get("radial_velocity_mps", contact.get("vel_mps", 0.0))),
                    "rcs_m2": float(contact.get("rcs_m2", 10.0 ** (float(contact.get("rcs_dbsm", -20.0)) / 10.0))),
                    "snr_db": float(contact.get("snr_db", 10.0)),
                    "confidence": float(contact.get("confidence", 0.95)),
                    "metadata": {
                        "source_format": "rps82",
                        "track_quality": contact.get("track_quality", "nominal"),
                    },
                }
            )

        wrapped = {
            "scan_id": raw_scan.get("scan_id", raw_scan.get("frame_id", "")),
            "scan_index": raw_scan.get("scan_index", raw_scan.get("frame", 0)),
            "scan_mode": raw_scan.get("scan_mode", "SECTOR"),
            "timestamp": raw_scan.get("timestamp"),
            "plots": normalized_plots,
        }
        return super().parse_raw_scan(wrapped)
