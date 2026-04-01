"""OpenWeatherMap adapter for cross-validation weather and alerts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import OWMConfig
from .normalizer import OWMNormalizer


class OpenWeatherMapAdapter(ProviderAdapter):
    provider_id = "weather-owm"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = OWMConfig()
        self.normalizer = OWMNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "weather-owm" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="WEATHER_ENVIRONMENT",
            tier="FREEMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["OPENWEATHERMAP_API_KEY"],
            description="OpenWeatherMap cross-validation source for current weather, AQI, and alerts.",
        )

    def _resolve_location(self, location: str) -> dict[str, float | str]:
        if location in self.config.saudi_locations:
            return self.config.saudi_locations[location]
        if "," in location:
            lat_s, lon_s = [part.strip() for part in location.split(",", 1)]
            return {"lat": float(lat_s), "lon": float(lon_s), "name": f"Custom ({lat_s},{lon_s})"}
        raise ValueError(f"Unknown location '{location}'")

    def _api_key(self) -> str:
        return self._env("OPENWEATHERMAP_API_KEY")

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "current_riyadh.json").exists()
        return bool(self._api_key())

    def _request_json(self, path: str, query: dict[str, Any]) -> dict[str, Any]:
        full_url = f"{self.config.base_url}{path}?{parse.urlencode(query)}"
        with request.urlopen(full_url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_current(self, location: str = "riyadh") -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "current_riyadh.json")
            payload["location"] = loc
            return payload
        payload = self._request_json(
            "/data/2.5/weather",
            {"lat": loc["lat"], "lon": loc["lon"], "appid": self._api_key(), "units": "metric"},
        )
        payload["location"] = loc
        return payload

    def fetch_forecast(self, location: str = "riyadh") -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "forecast_riyadh.json")
            payload["location"] = loc
            return payload
        payload = self._request_json(
            "/data/2.5/forecast",
            {"lat": loc["lat"], "lon": loc["lon"], "appid": self._api_key(), "units": "metric"},
        )
        payload["location"] = loc
        return payload

    def fetch_air_quality(self, location: str = "riyadh") -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "air_quality_riyadh.json")
            payload["location"] = loc
            return payload
        payload = self._request_json(
            "/data/2.5/air_pollution",
            {"lat": loc["lat"], "lon": loc["lon"], "appid": self._api_key()},
        )
        payload["location"] = loc
        return payload

    def fetch_alerts(self, location: str = "riyadh") -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "alerts_sandstorm.json")
            payload["location"] = loc
            return payload
        payload = self._request_json(
            "/data/3.0/onecall",
            {"lat": loc["lat"], "lon": loc["lon"], "appid": self._api_key(), "exclude": "minutely"},
        )
        payload["location"] = loc
        return payload

    def fetch_all_saudi_current(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in self.config.saudi_locations:
            out[key] = self.fetch_current(key)
        return {"locations": out, "count": len(out)}

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "current")
        if action == "forecast":
            return self.fetch_forecast(params.get("location", "riyadh"))
        if action == "air_quality":
            return self.fetch_air_quality(params.get("location", "riyadh"))
        if action == "alerts":
            return self.fetch_alerts(params.get("location", "riyadh"))
        if action == "all_saudi":
            return self.fetch_all_saudi_current()
        return self.fetch_current(params.get("location", "riyadh"))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "main" in raw_data and "wind" in raw_data:
            return self.normalizer.normalize_current(raw_data, raw_data["location"])
        if isinstance(raw_data, dict) and "list" in raw_data and raw_data.get("list") and "dt_txt" in raw_data["list"][0]:
            return self.normalizer.normalize_forecast(raw_data.get("list", []), raw_data["location"])
        if isinstance(raw_data, dict) and "list" in raw_data and raw_data.get("list") and "components" in raw_data["list"][0]:
            return self.normalizer.normalize_air_quality(raw_data, raw_data["location"], self.config.aqi_levels)
        if isinstance(raw_data, dict) and "alerts" in raw_data:
            return self.normalizer.normalize_alerts(raw_data.get("alerts", []))
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            self.fetch_current("riyadh")
            status = "ok"
            detail = "OWM current weather endpoint or fixture reachable."
        except Exception as exc:  # pragma: no cover
            status = "degraded"
            detail = str(exc)
        return {"status": status, "latency": round((time.perf_counter() - start) * 1000.0, 2), "detail": detail}
