"""Pre-built simulation-only DroneKit scenario library for S3M tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TestScenarioLibrary:
    """Deterministic scripted scenarios for SITL-only mission validation."""

    @staticmethod
    def _event(name: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "event": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": detail or {},
        }

    def square_patrol(self, vehicle: Any, size_m: int = 100, alt_m: int = 20) -> list[dict[str, Any]]:
        _ = vehicle
        return [
            self._event("takeoff", {"alt_m": alt_m}),
            self._event("waypoint", {"index": 1, "offset_m": (size_m, 0)}),
            self._event("waypoint", {"index": 2, "offset_m": (size_m, size_m)}),
            self._event("waypoint", {"index": 3, "offset_m": (0, size_m)}),
            self._event("waypoint", {"index": 4, "offset_m": (0, 0)}),
            self._event("rtl", {"reason": "patrol_complete"}),
        ]

    def waypoint_mission(self, vehicle: Any, waypoints: list[tuple[float, float, float]]) -> list[dict[str, Any]]:
        _ = vehicle
        events = [self._event("mission_upload", {"waypoints": len(waypoints)})]
        for idx, wp in enumerate(waypoints, start=1):
            events.append(self._event("waypoint_reached", {"index": idx, "position": list(wp)}))
        events.append(self._event("mission_complete", {"mode": "AUTO"}))
        return events

    def gps_denial_test(self, vehicle: Any) -> list[dict[str, Any]]:
        _ = vehicle
        return [
            self._event("takeoff", {"alt_m": 20}),
            self._event("navigate", {"phase": "pre-denial"}),
            self._event("gps_denied", {"fix_type": 0, "satellites": 0}),
            self._event("fallback_triggered", {"component": "phase8_navigation"}),
            self._event("rtl", {"reason": "gps_denial"}),
        ]

    def envelope_violation_test(self, vehicle: Any, geofence: list[tuple[float, float]]) -> list[dict[str, Any]]:
        _ = vehicle
        return [
            self._event("takeoff", {"alt_m": 15}),
            self._event("geofence_loaded", {"vertices": len(geofence)}),
            self._event("boundary_crossed", {"expected": "hool_safe_mode"}),
            self._event("hool_response", {"action": "safe_mode_or_rtb"}),
        ]

    def battery_low_test(self, vehicle: Any, threshold_pct: int = 20) -> list[dict[str, Any]]:
        _ = vehicle
        return [
            self._event("takeoff", {"alt_m": 10}),
            self._event("battery_drain_simulation", {"threshold_pct": threshold_pct}),
            self._event("battery_low_trigger", {"remaining_pct": threshold_pct - 1}),
            self._event("rtb", {"reason": "battery_low"}),
        ]

    def comms_loss_test(self, vehicle: Any, loss_duration_s: int = 120) -> list[dict[str, Any]]:
        _ = vehicle
        return [
            self._event("mission_start", {"mode": "GUIDED"}),
            self._event("heartbeat_loss", {"duration_s": loss_duration_s}),
            self._event("lost_link_procedure", {"component": "hool"}),
            self._event("rtl", {"reason": "comms_loss"}),
        ]
