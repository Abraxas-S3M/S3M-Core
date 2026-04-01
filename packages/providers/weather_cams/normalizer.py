"""Normalizer utilities for CAMS dust and atmospheric risk outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.weather.models import NormalizedWeatherObservation

from .config import DUST_AOD_THRESHOLDS


class CAMSNormalizer:
    provider_id = "weather-cams"
    provider_name = "Copernicus CAMS"

    def classify_dust_risk(self, aod: float) -> str:
        if aod < DUST_AOD_THRESHOLDS["clear"]:
            return "clear"
        if aod < DUST_AOD_THRESHOLDS["light_haze"]:
            return "light_haze"
        if aod < DUST_AOD_THRESHOLDS["moderate_dust"]:
            return "moderate_dust"
        if aod < DUST_AOD_THRESHOLDS["heavy_dust"]:
            return "heavy_dust"
        if aod < DUST_AOD_THRESHOLDS["sandstorm"]:
            return "sandstorm"
        return "severe_storm"

    def estimate_visibility_from_aod(self, aod: float) -> float:
        visibility = 3.0 / (aod + 0.05)
        return max(0.1, min(100.0, visibility))

    def normalize_dust_observation(
        self,
        data: dict[str, Any],
        location: dict[str, float | str],
        forecast_hours: int = 0,
    ) -> NormalizedWeatherObservation:
        aod = float(data.get("dust_aod", 0.0))
        pm10 = float(data.get("pm10", 0.0))
        risk = self.classify_dust_risk(aod)
        return NormalizedWeatherObservation(
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(data.get("timestamp", "")),
                confidence=0.90,
                classification="UNCLASSIFIED",
            ),
            timestamp=datetime.fromisoformat(str(data.get("timestamp", "1970-01-01T00:00:00+00:00")).replace("Z", "+00:00")),
            geo_point=GeoPoint(lat=float(location["lat"]), lon=float(location["lon"])),
            tags=[str(location["name"]), "dust_risk_level:" + risk, "source_model:CAMS"],
            temperature_c=0.0,
            humidity_pct=0.0,
            wind_speed_mps=0.0,
            wind_direction_deg=0.0,
            visibility_km=self.estimate_visibility_from_aod(aod),
            precipitation_mm=0.0,
            pressure_hpa=0.0,
            cloud_cover_pct=0.0,
            uv_index=float(data.get("uv_index", 0.0)),
            dust_concentration=pm10,
            forecast_hours=forecast_hours,
        )

    def generate_dust_alerts(
        self,
        dust_timeline: list[dict[str, Any]],
        thresholds: dict[str, float],
        affected_locations: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for row in dust_timeline:
            aod = float(row.get("aod", row.get("dust_aod", 0.0)))
            if aod < thresholds["heavy_dust"]:
                continue
            severity = "warning"
            if aod >= thresholds["sandstorm"]:
                severity = "critical"
            alerts.append(
                {
                    "type": "dust",
                    "severity": severity,
                    "aod_peak": aod,
                    "pm10_peak": float(row.get("pm10", 0.0)),
                    "onset_time": row.get("timestamp"),
                    "expected_duration_hours": int(row.get("duration_hours", 6)),
                    "affected_locations": affected_locations or row.get("affected_locations", []),
                }
            )
        return alerts
