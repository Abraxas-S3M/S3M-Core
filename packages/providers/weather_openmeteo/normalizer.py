"""Normalization and operational alert logic for Open-Meteo weather data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.weather.models import NormalizedWeatherObservation

from .config import OPERATIONAL_THRESHOLDS


class OpenMeteoNormalizer:
    provider_id = "weather-openmeteo"
    provider_name = "Open-Meteo"

    def _confidence_for_hour(self, forecast_hours: int) -> float:
        if forecast_hours <= 24:
            return 0.95
        if forecast_hours <= 72:
            return 0.85
        return 0.70

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def normalize_hourly(
        self,
        hourly_data: dict[str, list[Any]],
        location: dict[str, float | str],
    ) -> list[NormalizedWeatherObservation]:
        timestamps = hourly_data.get("time", [])
        out: list[NormalizedWeatherObservation] = []
        fetched_at = self._now_utc()
        lat = float(location["lat"])
        lon = float(location["lon"])
        loc_name = str(location["name"])
        for idx, ts in enumerate(timestamps):
            wind_kmh = float((hourly_data.get("wind_speed_10m") or [0.0])[idx])
            visibility_m = float((hourly_data.get("visibility") or [0.0])[idx])
            dust = hourly_data.get("dust", [])
            dust_value = float(dust[idx]) if idx < len(dust) and dust[idx] is not None else None
            forecast_hours = idx
            tags = [loc_name, "forecast" if idx > 0 else "observation"]
            if dust_value is not None and dust_value >= OPERATIONAL_THRESHOLDS["dust_sandstorm_threshold_ugm3"]:
                tags.append("sandstorm_risk")
            if visibility_m < OPERATIONAL_THRESHOLDS["visibility_flight_min_m"]:
                tags.append("low_visibility")
            if wind_kmh > OPERATIONAL_THRESHOLDS["wind_max_uav_kmh"]:
                tags.append("high_wind")
            out.append(
                NormalizedWeatherObservation(
                    provenance=Provenance(
                        provider_id=self.provider_id,
                        provider_name=self.provider_name,
                        fetched_at=fetched_at,
                        raw_id=str(ts),
                        confidence=self._confidence_for_hour(forecast_hours),
                        classification="UNCLASSIFIED",
                    ),
                    timestamp=datetime.fromisoformat(str(ts).replace("Z", "+00:00")),
                    geo_point=GeoPoint(lat=lat, lon=lon),
                    tags=tags,
                    temperature_c=float((hourly_data.get("temperature_2m") or [0.0])[idx]),
                    humidity_pct=float((hourly_data.get("relative_humidity_2m") or [0.0])[idx]),
                    wind_speed_mps=wind_kmh / 3.6,
                    wind_direction_deg=float((hourly_data.get("wind_direction_10m") or [0.0])[idx]),
                    visibility_km=visibility_m / 1000.0,
                    precipitation_mm=float((hourly_data.get("precipitation") or [0.0])[idx]),
                    pressure_hpa=float((hourly_data.get("surface_pressure") or [0.0])[idx]),
                    cloud_cover_pct=float((hourly_data.get("cloud_cover") or [0.0])[idx]),
                    uv_index=float((hourly_data.get("uv_index") or [0.0])[idx]),
                    dust_concentration=dust_value,
                    forecast_hours=forecast_hours,
                )
            )
        return out

    def normalize_marine(self, marine_data: dict[str, list[Any]], location: dict[str, float | str]) -> list[dict[str, Any]]:
        timestamps = marine_data.get("time", [])
        out: list[dict[str, Any]] = []
        for idx, ts in enumerate(timestamps):
            wave_height = float((marine_data.get("wave_height") or [0.0])[idx])
            out.append(
                {
                    "timestamp": ts,
                    "location": location["name"],
                    "wave_height_m": wave_height,
                    "wave_period_s": float((marine_data.get("wave_period") or [0.0])[idx]),
                    "wave_direction_deg": float((marine_data.get("wave_direction") or [0.0])[idx]),
                    "swell_m": float((marine_data.get("swell_wave_height") or [0.0])[idx]),
                    "current_velocity_ms": float((marine_data.get("ocean_current_velocity") or [0.0])[idx]),
                    "sea_state_go": wave_height <= OPERATIONAL_THRESHOLDS["wave_max_usv_m"],
                }
            )
        return out

    def normalize_air_quality(self, aq_data: dict[str, list[Any]], location: dict[str, float | str]) -> list[dict[str, Any]]:
        timestamps = aq_data.get("time", [])
        out: list[dict[str, Any]] = []
        for idx, ts in enumerate(timestamps):
            dust_value = float((aq_data.get("dust") or [0.0])[idx])
            if dust_value < 50:
                risk = "none"
            elif dust_value < 200:
                risk = "moderate"
            elif dust_value <= 500:
                risk = "severe"
            else:
                risk = "extreme"
            out.append(
                {
                    "timestamp": ts,
                    "location": location["name"],
                    "pm10": float((aq_data.get("pm10") or [0.0])[idx]),
                    "pm2_5": float((aq_data.get("pm2_5") or [0.0])[idx]),
                    "dust_ugm3": dust_value,
                    "aod": float((aq_data.get("aerosol_optical_depth") or [0.0])[idx]),
                    "uv_index": float((aq_data.get("uv_index") or [0.0])[idx]),
                    "sandstorm_risk": risk,
                }
            )
        return out

    def generate_operational_alerts(
        self,
        observations: list[NormalizedWeatherObservation],
        thresholds: dict[str, float],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for obs in observations:
            valid_from = obs.timestamp.isoformat()
            valid_until = obs.timestamp.isoformat()
            if (obs.dust_concentration or 0.0) > thresholds["dust_severe_storm_ugm3"]:
                alerts.append(
                    {
                        "type": "sandstorm",
                        "severity": "critical",
                        "detail": "Severe sandstorm conditions detected; halt all outdoor operations.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["flight", "ground", "uav", "maritime", "personnel"],
                    }
                )
            elif (obs.dust_concentration or 0.0) > thresholds["dust_sandstorm_threshold_ugm3"]:
                alerts.append(
                    {
                        "type": "sandstorm",
                        "severity": "warning",
                        "detail": "Sandstorm risk rising; restrict exposed operations and sensor use.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["flight", "ground", "uav", "personnel"],
                    }
                )
            if obs.temperature_c > thresholds["temperature_max_operations_c"]:
                alerts.append(
                    {
                        "type": "heat",
                        "severity": "critical",
                        "detail": "Extreme heat above mission safety threshold; rotate crews and reduce tempo.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["ground", "maintenance", "personnel"],
                    }
                )
            visibility_m = obs.visibility_km * 1000.0
            if visibility_m < thresholds["visibility_ground_ops_min_m"]:
                alerts.append(
                    {
                        "type": "visibility",
                        "severity": "critical",
                        "detail": "Ground visibility below 500m; vehicle operations NO-GO.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["ground"],
                    }
                )
            elif visibility_m < thresholds["visibility_flight_min_m"]:
                alerts.append(
                    {
                        "type": "visibility",
                        "severity": "warning",
                        "detail": "Flight visibility below VFR minimums; aviation operations NO-GO.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["flight"],
                    }
                )
            wind_kmh = obs.wind_speed_mps * 3.6
            if wind_kmh > thresholds["wind_max_helicopter_kmh"]:
                alerts.append(
                    {
                        "type": "wind",
                        "severity": "critical",
                        "detail": "Winds exceed helicopter threshold; rotary operations NO-GO.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["flight", "helicopter"],
                    }
                )
            elif wind_kmh > thresholds["wind_max_uav_kmh"]:
                alerts.append(
                    {
                        "type": "wind",
                        "severity": "warning",
                        "detail": "Winds exceed UAV threshold; small UAV operations NO-GO.",
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "affected_ops": ["uav"],
                    }
                )
        return alerts
