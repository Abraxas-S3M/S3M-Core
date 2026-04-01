"""Windward normalizer for maritime risk intelligence payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.maritime.models import NormalizedVesselTrack

from .config import WindwardConfig


class WindwardNormalizer:
    """Normalize Windward risk, alert, and ownership structures."""

    def __init__(self, provider_id: str = "maritime-windward", provider_name: str = "Windward") -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.config = WindwardConfig()

    def _risk_level(self, score: int) -> str:
        if score >= self.config.risk_level_thresholds["critical"]:
            return "critical"
        if score >= self.config.risk_level_thresholds["high"]:
            return "high"
        if score >= self.config.risk_level_thresholds["medium"]:
            return "medium"
        return "low"

    def _dark_indicator_score(self, profile: dict[str, Any]) -> int:
        for item in profile.get("risk_indicators", []):
            if item.get("type") == "dark_activity":
                try:
                    return int(item.get("score", 0))
                except (TypeError, ValueError):
                    return 0
        return 0

    def normalize_risk_profile(self, profile: dict[str, Any]) -> NormalizedVesselTrack:
        mmsi = str(profile.get("mmsi", ""))
        score = int(profile.get("risk_score", 0) or 0)
        risk_level = str(profile.get("risk_level") or self._risk_level(score))
        indicators = [str(item.get("type", "")) for item in profile.get("risk_indicators", []) if item.get("type")]
        sanctions = bool((profile.get("sanctions_screening") or {}).get("proximity_to_listed", False))
        dark_score = self._dark_indicator_score(profile)
        is_dark = dark_score > 50

        tags = [f"risk_level:{risk_level}", f"risk_score:{score}"] + [f"indicator:{ind}" for ind in indicators]
        tags.append("sanctions:proximity" if sanctions else "sanctions:none")

        # Tactical context: AI-derived risk analytics prioritize interception resources.
        provenance = Provenance(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            fetched_at=datetime.now(timezone.utc),
            raw_id=mmsi,
            confidence=0.90,
            classification="UNCLASSIFIED",
        )
        track = NormalizedVesselTrack(
            mmsi=mmsi,
            vessel_name=str(profile.get("vessel_name", f"Vessel-{mmsi}")),
            vessel_type=str(profile.get("vessel_type", "Unknown")),
            flag_state=str(profile.get("flag_state", "")),
            speed_knots=0.0,
            course_deg=0.0,
            heading_deg=0.0,
            destination=None,
            eta=None,
            nav_status="risk_profile",
            draught_m=None,
            length_m=None,
            is_dark=is_dark,
            provenance=provenance,
            timestamp=datetime.now(timezone.utc),
            geo_point=GeoPoint(
                lat=float((profile.get("position") or {}).get("lat", 0.0)),
                lon=float((profile.get("position") or {}).get("lon", 0.0)),
            ),
            tags=tags,
            raw_data_ref=mmsi,
        )
        # Dynamic metadata fields for downstream tactical fusion engines.
        setattr(track, "risk_score", score)
        setattr(track, "risk_level", risk_level)
        setattr(track, "risk_indicators", indicators)
        setattr(track, "sanctions_proximity", sanctions)
        return track

    def normalize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        return {
            "mmsi": str(alert.get("mmsi", "")),
            "alert_type": str(alert.get("type", "")),
            "severity": str(alert.get("severity", "low")),
            "detail": alert.get("detail"),
            "timestamp": str(alert.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "position": {
                "lat": float((alert.get("position") or {}).get("lat", 0.0)),
                "lon": float((alert.get("position") or {}).get("lon", 0.0)),
            },
        }

    def normalize_ownership(self, ownership: dict[str, Any]) -> dict[str, Any]:
        return {
            "mmsi": str(ownership.get("mmsi", "")),
            "beneficial_owner": ownership.get("beneficial_owner"),
            "registered_owner": ownership.get("registered_owner"),
            "operator": ownership.get("operator"),
            "flag_history": list(ownership.get("flag_history", [])),
        }

    def risk_to_border_alert(self, risk_profile: dict[str, Any]) -> dict[str, Any]:
        mmsi = str(risk_profile.get("mmsi", ""))
        level = str(risk_profile.get("risk_level", self._risk_level(int(risk_profile.get("risk_score", 0) or 0))))
        indicators = [str(item.get("type", "")) for item in risk_profile.get("risk_indicators", []) if item.get("type")]
        alert_type = "risk_vessel"
        if "dark_activity" in indicators:
            alert_type = "dark_vessel"
        elif "sanctions_proximity" in indicators:
            alert_type = "sanctions_vessel"
        elif "sts_transfer" in indicators:
            alert_type = "suspicious_transfer"
        return {
            "mmsi": mmsi,
            "zone_id": risk_profile.get("zone_id", "maritime-risk"),
            "alert_type": alert_type,
            "severity": level,
            "description": f"Windward risk alert for {mmsi}: {', '.join(indicators) if indicators else 'no indicators'}",
            "position": {
                "lat": float((risk_profile.get("position") or {}).get("lat", 0.0)),
                "lon": float((risk_profile.get("position") or {}).get("lon", 0.0)),
            },
            "confidence": 0.9,
        }
