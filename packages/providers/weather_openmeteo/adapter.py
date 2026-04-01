"""Open-Meteo adapter for forecast, marine, and dust-aware operations checks."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import OPERATIONAL_THRESHOLDS, SAUDI_LOCATIONS, OpenMeteoConfig
from .normalizer import OpenMeteoNormalizer


class OpenMeteoAdapter(ProviderAdapter):
    provider_id = "weather-openmeteo"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = OpenMeteoConfig()
        self.normalizer = OpenMeteoNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "weather-openmeteo" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="WEATHER_ENVIRONMENT",
            tier="FREE",
            auth_type="none",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            description="Open weather forecast with tactical dust/visibility monitoring for Saudi operations.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "forecast_riyadh.json").exists()
        # Tactical context: no credentials required, so endpoint reachability is sufficient.
        return True

    def _resolve_location(self, location: str) -> dict[str, float | str]:
        if location in self.config.saudi_locations:
            return self.config.saudi_locations[location]
        if "," in location:
            lat_s, lon_s = [part.strip() for part in location.split(",", 1)]
            return {"lat": float(lat_s), "lon": float(lon_s), "name": f"Custom ({lat_s},{lon_s})"}
        raise ValueError(f"Unknown location '{location}'")

    def _request_json(self, url: str, query: dict[str, Any]) -> dict[str, Any]:
        full_url = f"{url}?{parse.urlencode(query)}"
        with request.urlopen(full_url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_forecast(self, location: str = "riyadh", days: int = 7) -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            fixture_name = "forecast_riyadh.json" if location == "riyadh" else "forecast_jubail.json"
            payload = self._read_json(self.fixture_dir / fixture_name)
            return {
                "location": loc["name"],
                "hourly": payload.get("hourly", {}),
                "daily": payload.get("daily", {}),
                "forecast_days": days,
            }
        payload = self._request_json(
            self.config.forecast_url,
            {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "hourly": ",".join(self.config.hourly_params),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                "timezone": self.config.timezone,
                "forecast_days": days,
            },
        )
        return {
            "location": loc["name"],
            "hourly": payload.get("hourly", {}),
            "daily": payload.get("daily", {}),
            "forecast_days": days,
        }

    def fetch_marine_forecast(self, location: str = "strait_of_hormuz", days: int = 7) -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "marine_hormuz.json")
            return {"location": loc["name"], "hourly": payload.get("hourly", {}), "forecast_days": days}
        payload = self._request_json(
            self.config.marine_url,
            {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "hourly": ",".join(self.config.marine_params),
                "timezone": self.config.timezone,
                "forecast_days": days,
            },
        )
        return {"location": loc["name"], "hourly": payload.get("hourly", {}), "forecast_days": days}

    def fetch_air_quality(self, location: str = "riyadh", days: int = 5) -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "air_quality_riyadh.json")
            return {"location": loc["name"], "hourly": payload.get("hourly", {}), "forecast_days": days}
        payload = self._request_json(
            self.config.air_quality_url,
            {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "hourly": ",".join(self.config.air_quality_params),
                "timezone": self.config.timezone,
                "forecast_days": days,
            },
        )
        return {"location": loc["name"], "hourly": payload.get("hourly", {}), "forecast_days": days}

    def fetch_historical(self, location: str, start_date: str, end_date: str) -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            return self.fetch_forecast(location, days=3)
        payload = self._request_json(
            self.config.archive_url,
            {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "start_date": start_date,
                "end_date": end_date,
                "hourly": "temperature_2m,wind_speed_10m,visibility,dust",
                "timezone": self.config.timezone,
            },
        )
        return {"location": loc["name"], "hourly": payload.get("hourly", {}), "daily": payload.get("daily", {})}

    def fetch_all_saudi_locations(self, days: int = 3) -> dict[str, Any]:
        locations: dict[str, Any] = {}
        alerts: list[dict[str, Any]] = []
        for key in self.config.saudi_locations:
            forecast = self.fetch_forecast(key, days=days)
            loc = self._resolve_location(key)
            observations = self.normalizer.normalize_hourly(forecast.get("hourly", {}), loc)
            alerts.extend(self.normalizer.generate_operational_alerts(observations[:24], self.config.operational_thresholds))
            locations[key] = forecast
        return {"locations": locations, "alerts": alerts}

    def check_operational_conditions(self, location: str) -> dict[str, Any]:
        forecast = self.fetch_forecast(location=location, days=2)
        loc = self._resolve_location(location)
        observations = self.normalizer.normalize_hourly(forecast.get("hourly", {}), loc)
        horizon = observations[:24] if observations else []
        alerts = self.normalizer.generate_operational_alerts(horizon, self.config.operational_thresholds)
        flight = "GO"
        ground = "GO"
        uav = "GO"
        maritime = "GO"
        for obs in horizon:
            visibility_m = obs.visibility_km * 1000.0
            wind_kmh = obs.wind_speed_mps * 3.6
            dust = obs.dust_concentration or 0.0
            if visibility_m < OPERATIONAL_THRESHOLDS["visibility_flight_min_m"] or dust >= OPERATIONAL_THRESHOLDS["dust_severe_storm_ugm3"]:
                flight = "NO-GO"
            elif visibility_m < OPERATIONAL_THRESHOLDS["visibility_flight_min_m"] * 1.5 or dust >= OPERATIONAL_THRESHOLDS["dust_sandstorm_threshold_ugm3"]:
                flight = "CAUTION" if flight == "GO" else flight
            if visibility_m < OPERATIONAL_THRESHOLDS["visibility_ground_ops_min_m"] or dust >= OPERATIONAL_THRESHOLDS["dust_severe_storm_ugm3"]:
                ground = "NO-GO"
            elif visibility_m < 1000 or dust >= OPERATIONAL_THRESHOLDS["dust_sandstorm_threshold_ugm3"]:
                ground = "CAUTION" if ground == "GO" else ground
            if wind_kmh > OPERATIONAL_THRESHOLDS["wind_max_uav_kmh"] or dust >= OPERATIONAL_THRESHOLDS["dust_sandstorm_threshold_ugm3"]:
                uav = "NO-GO"
            elif wind_kmh > OPERATIONAL_THRESHOLDS["wind_max_uav_kmh"] * 0.75:
                uav = "CAUTION" if uav == "GO" else uav
        marine = self.fetch_marine_forecast(location="strait_of_hormuz", days=2)
        marine_rows = self.normalizer.normalize_marine(marine.get("hourly", {}), self._resolve_location("strait_of_hormuz"))
        if any(item["wave_height_m"] > OPERATIONAL_THRESHOLDS["wave_max_patrol_boat_m"] for item in marine_rows):
            maritime = "NO-GO"
        elif any(item["wave_height_m"] > OPERATIONAL_THRESHOLDS["wave_max_usv_m"] for item in marine_rows):
            maritime = "CAUTION"
        return {
            "location": loc["name"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "flight_ops": flight,
            "ground_ops": ground,
            "uav_ops": uav,
            "maritime_ops": maritime,
            "alerts": alerts,
        }

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "forecast")
        if action == "marine":
            return self.fetch_marine_forecast(params.get("location", "strait_of_hormuz"), int(params.get("days", 7)))
        if action == "air_quality":
            return self.fetch_air_quality(params.get("location", "riyadh"), int(params.get("days", 5)))
        if action == "historical":
            return self.fetch_historical(params.get("location", "riyadh"), params.get("start_date"), params.get("end_date"))
        if action == "all_saudi":
            return self.fetch_all_saudi_locations(int(params.get("days", 3)))
        if action == "operational":
            return self.check_operational_conditions(params.get("location", "riyadh"))
        return self.fetch_forecast(params.get("location", "riyadh"), int(params.get("days", 7)))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "hourly" in raw_data and "location" in raw_data:
            loc = None
            for item in SAUDI_LOCATIONS.values():
                if item["name"] == raw_data["location"]:
                    loc = item
                    break
            if loc is None:
                loc = {"lat": 24.71, "lon": 46.68, "name": raw_data["location"]}
            observations = self.normalizer.normalize_hourly(raw_data.get("hourly", {}), loc)
            return {"observations": observations, "count": len(observations)}
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            self.fetch_forecast("riyadh", 1)
            status = "ok"
            detail = "Open-Meteo forecast endpoint or air-gapped fixture reachable."
        except Exception as exc:  # pragma: no cover
            status = "degraded"
            detail = str(exc)
        return {"status": status, "latency": round((time.perf_counter() - start) * 1000.0, 2), "detail": detail}
