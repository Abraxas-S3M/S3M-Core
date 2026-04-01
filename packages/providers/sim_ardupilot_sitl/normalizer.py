"""Normalization helpers for simulation-only ArduPilot SITL telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ArduPilotSITLNormalizer:
    """Convert SITL telemetry into shared S3M autonomy and HOOL contracts."""

    @staticmethod
    def normalize_telemetry(telemetry: dict[str, Any]) -> dict[str, Any]:
        timestamp = str(telemetry.get("timestamp") or datetime.now(timezone.utc).isoformat())
        return {
            "position": {
                "lat": float(telemetry.get("lat", 0.0)),
                "lon": float(telemetry.get("lon", 0.0)),
                "alt": float(telemetry.get("alt", 0.0)),
            },
            "attitude": {
                "roll": float(telemetry.get("roll", 0.0)),
                "pitch": float(telemetry.get("pitch", 0.0)),
                "yaw": float(telemetry.get("yaw", 0.0)),
            },
            "velocity": {
                "groundspeed": float(telemetry.get("groundspeed", 0.0)),
                "airspeed": float(telemetry.get("airspeed", 0.0)),
            },
            "battery": {
                "voltage": float(telemetry.get("battery_voltage", telemetry.get("voltage", 0.0))),
                "current": float(telemetry.get("battery_current", telemetry.get("current", 0.0))),
                "remaining_pct": float(telemetry.get("battery_pct", telemetry.get("remaining_pct", 0.0))),
            },
            "gps": {
                "fix_type": int(telemetry.get("gps_fix", telemetry.get("fix_type", 0))),
                "satellites": int(telemetry.get("satellites", 0)),
            },
            "mode": str(telemetry.get("mode", "UNKNOWN")),
            "armed": bool(telemetry.get("armed", False)),
            "timestamp": timestamp,
        }

    def telemetry_to_sensor_data(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        norm = self.normalize_telemetry(telemetry)
        return {
            "position": (
                norm["position"]["lat"],
                norm["position"]["lon"],
                norm["position"]["alt"],
            ),
            "heading": float(telemetry.get("heading", 0.0)),
            "speed": norm["velocity"]["groundspeed"],
            "battery_pct": norm["battery"]["remaining_pct"],
            "comms_status": "nominal",
            "mode": norm["mode"],
        }

    def telemetry_to_hool_state(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        norm = self.normalize_telemetry(telemetry)
        return {
            "current_position": (
                norm["position"]["lat"],
                norm["position"]["lon"],
                norm["position"]["alt"],
            ),
            "battery_pct": norm["battery"]["remaining_pct"],
            "fuel_pct": norm["battery"]["remaining_pct"],
            "comms_status": "nominal" if norm["mode"] != "LOST_LINK" else "lost",
            "risk_score": 0.1 if norm["gps"]["fix_type"] > 0 else 0.6,
            "targets_engaged": 0,
            "proposed_action": "patrol" if norm["mode"] not in {"RTL", "LAND"} else "rtb",
            "proposed_escalation_level": 1,
            "target": {"type": None, "confidence": 0.0},
        }
