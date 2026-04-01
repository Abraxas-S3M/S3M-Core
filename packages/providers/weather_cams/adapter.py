"""CAMS adapter focused on atmospheric dust and aerosol operational intelligence."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import CAMSConfig
from .normalizer import CAMSNormalizer


class CAMSAdapter(ProviderAdapter):
    provider_id = "weather-cams"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = CAMSConfig()
        self.normalizer = CAMSNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "weather-cams" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="WEATHER_ENVIRONMENT",
            tier="FREE",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["CAMS_API_KEY"],
            description="Copernicus atmosphere model for Saudi dust belt forecasts and aerosol intelligence.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "dust_forecast_riyadh.json").exists()
        return bool(self._env("CAMS_API_KEY"))

    def _resolve_location(self, location: str) -> dict[str, float | str]:
        if location in self.config.saudi_locations:
            return self.config.saudi_locations[location]
        if "," in location:
            lat_s, lon_s = [part.strip() for part in location.split(",", 1)]
            return {"lat": float(lat_s), "lon": float(lon_s), "name": f"Custom ({lat_s},{lon_s})"}
        raise ValueError(f"Unknown location '{location}'")

    def _request_json(self, query: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.forecast_api_url}?{parse.urlencode(query)}"
        with request.urlopen(url, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_dust_forecast(self, location: str = "riyadh", hours: int = 72) -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "dust_forecast_riyadh.json")
            data = payload if location == "riyadh" else {**payload, "location": loc["name"]}
        else:
            payload = self._request_json(
                {
                    "latitude": loc["lat"],
                    "longitude": loc["lon"],
                    "variables": ",".join(self.config.variables_atmospheric),
                    "forecast_hours": hours,
                }
            )
            data = {
                "location": loc["name"],
                "timestamps": payload.get("timestamps", []),
                "dust_aod": payload.get("dust_aod", []),
                "pm10": payload.get("pm10", []),
                "pm2_5": payload.get("pm2_5", []),
            }
        data["dust_risk_timeline"] = [self.normalizer.classify_dust_risk(float(v)) for v in data.get("dust_aod", [])]
        return data

    def fetch_regional_dust(self, bbox: dict[str, float] | None = None, hours: int = 48) -> dict[str, Any]:
        if self.is_airgapped:
            return self._read_json(self.fixture_dir / "regional_dust_saudi.json")
        area = bbox or self.config.saudi_bbox
        return self._request_json(
            {
                "north": area["north"],
                "west": area["west"],
                "south": area["south"],
                "east": area["east"],
                "variables": "dust_aod,pm10",
                "forecast_hours": hours,
            }
        )

    def fetch_pollution(self, location: str = "jubail", hours: int = 48) -> dict[str, Any]:
        if self.is_airgapped:
            return self._read_json(self.fixture_dir / "pollution_jubail.json")
        loc = self._resolve_location(location)
        return self._request_json(
            {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "variables": ",".join(self.config.variables_pollution),
                "forecast_hours": hours,
            }
        )

    def fetch_uv_forecast(self, location: str = "riyadh", hours: int = 48) -> dict[str, Any]:
        loc = self._resolve_location(location)
        if self.is_airgapped:
            data = self.fetch_dust_forecast(location, hours)
            return {"location": data["location"], "timestamps": data["timestamps"], "uv": [8.0 for _ in data["timestamps"]]}
        return self._request_json(
            {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "variables": "uv_index",
                "forecast_hours": hours,
            }
        )

    def fetch_all_saudi_dust(self, hours: int = 48) -> dict[str, Any]:
        by_location: dict[str, Any] = {}
        peak_location = ""
        peak_aod = -1.0
        all_alerts: list[dict[str, Any]] = []
        for key in self.config.saudi_locations:
            dust_data = self.fetch_dust_forecast(key, hours=hours)
            by_location[key] = dust_data
            location_peak = max((float(v) for v in dust_data.get("dust_aod", []) or [0.0]), default=0.0)
            if location_peak > peak_aod:
                peak_aod = location_peak
                peak_location = key
            timeline = [
                {"timestamp": t, "aod": a, "pm10": p}
                for t, a, p in zip(dust_data.get("timestamps", []), dust_data.get("dust_aod", []), dust_data.get("pm10", []))
            ]
            alerts = self.normalizer.generate_dust_alerts(
                timeline,
                self.config.dust_aod_thresholds,
                affected_locations=[str(self.config.saudi_locations[key]["name"])],
            )
            all_alerts.extend(alerts)
        return {
            "locations": by_location,
            "peak_dust_location": peak_location,
            "peak_dust_aod": peak_aod,
            "sandstorm_alerts": all_alerts,
        }

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "dust")
        if action == "regional":
            return self.fetch_regional_dust(hours=int(params.get("hours", 48)))
        if action == "pollution":
            return self.fetch_pollution(params.get("location", "jubail"), int(params.get("hours", 48)))
        if action == "uv":
            return self.fetch_uv_forecast(params.get("location", "riyadh"), int(params.get("hours", 48)))
        if action == "all_saudi":
            return self.fetch_all_saudi_dust(int(params.get("hours", 48)))
        return self.fetch_dust_forecast(params.get("location", "riyadh"), int(params.get("hours", 72)))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and {"timestamps", "dust_aod", "pm10"}.issubset(raw_data.keys()):
            obs = []
            loc_name = raw_data.get("location", "Riyadh (Central Command)")
            loc = next((l for l in self.config.saudi_locations.values() if l["name"] == loc_name), self.config.saudi_locations["riyadh"])
            for idx, (ts, aod, pm10) in enumerate(
                zip(raw_data.get("timestamps", []), raw_data.get("dust_aod", []), raw_data.get("pm10", []))
            ):
                row = {
                    "timestamp": ts,
                    "dust_aod": aod,
                    "pm10": pm10,
                    "pm2_5": (raw_data.get("pm2_5", [0.0])[idx]),
                }
                obs.append(self.normalizer.normalize_dust_observation(row, loc, forecast_hours=idx))
            return {"observations": obs, "count": len(obs)}
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            data = self.fetch_dust_forecast("riyadh", 12)
            status = "ok"
            detail = f"dust forecast points={len(data.get('timestamps', []))}"
        except Exception as exc:  # pragma: no cover
            status = "degraded"
            detail = str(exc)
        return {"status": status, "latency": round((time.perf_counter() - start) * 1000.0, 2), "detail": detail}
