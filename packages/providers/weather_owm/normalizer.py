"""Normalization helpers for OpenWeatherMap weather and AQ feeds."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.weather.models import NormalizedWeatherObservation


class OWMNormalizer:
    provider_id = "weather-owm"
    provider_name = "OpenWeatherMap"

    def _parse_ts(self, value: Any) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def normalize_current(self, data: dict[str, Any], location: dict[str, float | str]) -> NormalizedWeatherObservation:
        weather_desc = (data.get("weather") or [{}])[0].get("description", "unknown")
        return NormalizedWeatherObservation(
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(data.get("dt", "current")),
                confidence=0.90,
                classification="UNCLASSIFIED",
            ),
            timestamp=self._parse_ts(data.get("dt", datetime.now(timezone.utc).isoformat())),
            geo_point=GeoPoint(lat=float(location["lat"]), lon=float(location["lon"])),
            tags=[str(location["name"]), "current", str(weather_desc)],
            temperature_c=float(data.get("main", {}).get("temp", 0.0)),
            humidity_pct=float(data.get("main", {}).get("humidity", 0.0)),
            wind_speed_mps=float(data.get("wind", {}).get("speed", 0.0)),
            wind_direction_deg=float(data.get("wind", {}).get("deg", 0.0)),
            visibility_km=float(data.get("visibility", 0.0)) / 1000.0,
            precipitation_mm=float((data.get("rain") or {}).get("1h", 0.0)),
            pressure_hpa=float(data.get("main", {}).get("pressure", 0.0)),
            cloud_cover_pct=float(data.get("clouds", {}).get("all", 0.0)),
            uv_index=None,
            dust_concentration=None,
            forecast_hours=0,
        )

    def normalize_forecast(self, forecast_list: list[dict[str, Any]], location: dict[str, float | str]) -> list[NormalizedWeatherObservation]:
        out: list[NormalizedWeatherObservation] = []
        if not forecast_list:
            return out
        base_ts = int(forecast_list[0].get("dt", 0))
        for row in forecast_list:
            dt_ts = int(row.get("dt", 0))
            forecast_hours = int((dt_ts - base_ts) / 3600)
            out.append(
                NormalizedWeatherObservation(
                    provenance=Provenance(
                        provider_id=self.provider_id,
                        provider_name=self.provider_name,
                        fetched_at=datetime.now(timezone.utc),
                        raw_id=str(dt_ts),
                        confidence=0.85,
                        classification="UNCLASSIFIED",
                    ),
                    timestamp=self._parse_ts(dt_ts),
                    geo_point=GeoPoint(lat=float(location["lat"]), lon=float(location["lon"])),
                    tags=[str(location["name"]), "forecast_3h"],
                    temperature_c=float(row.get("main", {}).get("temp", 0.0)),
                    humidity_pct=float(row.get("main", {}).get("humidity", 0.0)),
                    wind_speed_mps=float(row.get("wind", {}).get("speed", 0.0)),
                    wind_direction_deg=float(row.get("wind", {}).get("deg", 0.0)),
                    visibility_km=float(row.get("visibility", 0.0)) / 1000.0,
                    precipitation_mm=float((row.get("rain") or {}).get("3h", 0.0)),
                    pressure_hpa=float(row.get("main", {}).get("pressure", 0.0)),
                    cloud_cover_pct=float(row.get("clouds", {}).get("all", 0.0)),
                    uv_index=None,
                    dust_concentration=None,
                    forecast_hours=forecast_hours,
                )
            )
        return out

    def normalize_air_quality(self, aq_data: dict[str, Any], location: dict[str, float | str], aqi_levels: dict[int, str]) -> dict[str, Any]:
        first = (aq_data.get("list") or [{}])[0]
        aqi = int(first.get("main", {}).get("aqi", 1))
        components = first.get("components", {})
        return {
            "location": location["name"],
            "aqi": aqi,
            "aqi_label": aqi_levels.get(aqi, "unknown"),
            "pm10": float(components.get("pm10", 0.0)),
            "pm2_5": float(components.get("pm2_5", 0.0)),
            "dust_proxy": float(components.get("pm10", 0.0)),
        }

    def normalize_alerts(self, alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in alerts:
            out.append(
                {
                    "event": item.get("event", "Unknown"),
                    "severity": str(item.get("event", "unknown")).lower().replace(" ", "_"),
                    "detail": item.get("description", ""),
                    "valid_from": datetime.fromtimestamp(int(item.get("start", 0)), tz=timezone.utc).isoformat()
                    if item.get("start")
                    else None,
                    "valid_until": datetime.fromtimestamp(int(item.get("end", 0)), tz=timezone.utc).isoformat()
                    if item.get("end")
                    else None,
                    "source": item.get("sender_name", "OpenWeatherMap"),
                }
            )
        return out
