"""AIS anomaly detection for maritime surveillance operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from services.sensor_analytics.models import AISVessel, BorderAlert, BorderZone, make_alert


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


class AISAnomalyDetector:
    """Detects suspicious AIS behavior relevant to tactical maritime monitoring."""

    def __init__(self, zones: Optional[List[BorderZone]] = None) -> None:
        self.restricted_zones: List[Tuple[str, List[Tuple[float, float]]]] = []
        if zones:
            self.restricted_zones = [(zone.zone_id, zone.polygon) for zone in zones]

    def set_restricted_zones(self, zones: List[BorderZone]) -> None:
        """Update restricted zones used for intrusion anomaly checks."""
        self.restricted_zones = [(zone.zone_id, zone.polygon) for zone in zones]

    def detect_anomalies(self, vessel: AISVessel) -> List[dict]:
        anomalies: List[dict] = []
        now = datetime.now(timezone.utc)

        age_hours = (now - vessel.last_seen).total_seconds() / 3600.0
        if age_hours > 1.0:
            anomalies.append(
                {
                    "anomaly_type": "ais_gap",
                    "severity": "high",
                    "detail": f"AIS silence for {age_hours:.1f} hours",
                    "timestamp": now,
                    "position": vessel.last_position,
                }
            )

        if len(vessel.track) >= 2:
            prev = vessel.track[-2]
            curr = vessel.track[-1]
            prev_speed = float(prev.get("speed_knots", vessel.last_speed_knots))
            curr_speed = float(curr.get("speed_knots", vessel.last_speed_knots))
            if prev_speed > 0:
                delta_pct = abs(curr_speed - prev_speed) / prev_speed * 100.0
                if delta_pct > 50.0:
                    anomalies.append(
                        {
                            "anomaly_type": "speed_anomaly",
                            "severity": "medium",
                            "detail": f"Speed changed by {delta_pct:.1f}% in recent updates",
                            "timestamp": now,
                            "position": vessel.last_position,
                        }
                    )

            prev_course = float(prev.get("heading_deg", vessel.last_heading_deg))
            curr_course = float(curr.get("heading_deg", vessel.last_heading_deg))
            course_delta = abs(curr_course - prev_course)
            if course_delta > 180:
                course_delta = 360 - course_delta
            if course_delta > 90.0:
                anomalies.append(
                    {
                        "anomaly_type": "course_deviation",
                        "severity": "medium",
                        "detail": f"Heading changed by {course_delta:.1f} degrees",
                        "timestamp": now,
                        "position": vessel.last_position,
                    }
                )

            dist_km = _haversine_km(
                float(prev["lat"]),
                float(prev["lon"]),
                float(curr["lat"]),
                float(curr["lon"]),
            )
            if dist_km > 100.0:
                anomalies.append(
                    {
                        "anomaly_type": "position_spoofing",
                        "severity": "high",
                        "detail": f"Position jumped {dist_km:.1f} km between updates",
                        "timestamp": now,
                        "position": vessel.last_position,
                    }
                )

            low_speed_hours = 0.0
            for entry in reversed(vessel.track):
                if float(entry.get("speed_knots", 0.0)) < 1.0:
                    ts_text = str(entry["timestamp"])
                    if ts_text.endswith("Z"):
                        ts_text = ts_text[:-1] + "+00:00"
                    ts = datetime.fromisoformat(ts_text)
                    low_speed_hours = (now - ts).total_seconds() / 3600.0
                else:
                    break
            if low_speed_hours > 2.0:
                anomalies.append(
                    {
                        "anomaly_type": "loitering",
                        "severity": "low",
                        "detail": f"Loitering detected for {low_speed_hours:.1f} hours",
                        "timestamp": now,
                        "position": vessel.last_position,
                    }
                )

        zone_hit = self._restricted_zone_hit(vessel.last_position[0], vessel.last_position[1])
        if zone_hit is not None:
            anomalies.append(
                {
                    "anomaly_type": "zone_intrusion",
                    "severity": "high",
                    "detail": f"Vessel in restricted zone {zone_hit}",
                    "timestamp": now,
                    "position": vessel.last_position,
                    "zone_id": zone_hit,
                }
            )

        return anomalies

    def _restricted_zone_hit(self, lat: float, lon: float) -> Optional[str]:
        for zone_id, polygon in self.restricted_zones:
            if _point_in_polygon(lat, lon, polygon):
                return zone_id
        return None

    def detect_batch(self, vessels: List[AISVessel]) -> Dict[str, List[dict]]:
        return {v.mmsi: self.detect_anomalies(v) for v in vessels}

    def to_border_alerts(self, anomalies: List[dict], vessel: AISVessel) -> List[BorderAlert]:
        alerts: List[BorderAlert] = []
        for anomaly in anomalies:
            alerts.append(
                make_alert(
                    zone_id=str(anomaly.get("zone_id", "UNASSIGNED")),
                    alert_type=str(anomaly["anomaly_type"]),
                    severity=str(anomaly["severity"]),
                    position=tuple(anomaly["position"]),
                    description=str(anomaly["detail"]),
                    vessel_id=vessel.mmsi,
                    confidence=0.8 if anomaly["severity"] in {"high", "critical"} else 0.65,
                    evidence=[{"anomaly": anomaly, "vessel": vessel.to_dict()}],
                )
            )
        return alerts


def _point_in_polygon(lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
    x = lon
    y = lat
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[(i - 1) % n]
        xi = lon_i
        yi = lat_i
        xj = lon_j
        yj = lat_j
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
        )
        if intersects:
            inside = not inside
    return inside
