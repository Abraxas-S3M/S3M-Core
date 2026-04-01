"""Weather operations pipeline merging four weather/environment sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.providers._shared import BatchIngestionRunner, ProviderRegistry
from packages.providers.weather_openmeteo.config import OPERATIONAL_THRESHOLDS


class WeatherOperationsPipeline:
    def __init__(self) -> None:
        self.registry = ProviderRegistry()
        self.registry.register_weather_defaults()
        self.batch_runner = BatchIngestionRunner()
        self.thresholds = dict(OPERATIONAL_THRESHOLDS)

    def _compute_ops_status(self, current: Any, marine_wave_height: float | None = None) -> dict[str, str]:
        flight = "GO"
        ground = "GO"
        uav = "GO"
        maritime = "GO"

        vis_m = (float(getattr(current, "visibility_km", 0.0)) if current else 0.0) * 1000.0
        wind_kmh = (float(getattr(current, "wind_speed_mps", 0.0)) if current else 0.0) * 3.6
        dust = float(getattr(current, "dust_concentration", 0.0) or 0.0)

        if dust >= self.thresholds["dust_severe_storm_ugm3"] or vis_m < self.thresholds["visibility_flight_min_m"]:
            flight = "NO-GO"
        elif dust >= self.thresholds["dust_sandstorm_threshold_ugm3"]:
            flight = "CAUTION"

        if dust >= self.thresholds["dust_severe_storm_ugm3"] or vis_m < self.thresholds["visibility_ground_ops_min_m"]:
            ground = "NO-GO"
        elif dust >= self.thresholds["dust_sandstorm_threshold_ugm3"]:
            ground = "CAUTION"

        if wind_kmh > self.thresholds["wind_max_uav_kmh"] or dust >= self.thresholds["dust_sandstorm_threshold_ugm3"]:
            uav = "NO-GO"
        elif wind_kmh > self.thresholds["wind_max_uav_kmh"] * 0.75:
            uav = "CAUTION"

        if marine_wave_height is not None:
            if marine_wave_height > self.thresholds["wave_max_patrol_boat_m"]:
                maritime = "NO-GO"
            elif marine_wave_height > self.thresholds["wave_max_usv_m"]:
                maritime = "CAUTION"

        return {"flight": flight, "ground": ground, "uav": uav, "maritime": maritime}

    def _weighted_confidence(self, ndmc: Any | None, openmeteo: Any | None, owm: Any | None, cams: Any | None) -> float:
        weights = {
            "ndmc": 0.40,
            "openmeteo": 0.25,
            "owm": 0.20,
            "cams": 0.15,
        }
        values = {
            "ndmc": float(getattr(getattr(ndmc, "provenance", None), "confidence", 0.0) if ndmc else 0.0),
            "openmeteo": float(getattr(getattr(openmeteo, "provenance", None), "confidence", 0.0) if openmeteo else 0.0),
            "owm": float(getattr(getattr(owm, "provenance", None), "confidence", 0.0) if owm else 0.0),
            "cams": float(getattr(getattr(cams, "provenance", None), "confidence", 0.0) if cams else 0.0),
        }
        return round(sum(values[k] * weights[k] for k in weights), 3)

    def get_operational_weather(self, location: str = "riyadh") -> dict[str, Any]:
        openmeteo = self.registry.get("weather-openmeteo", "airgapped")
        owm = self.registry.get("weather-owm", "airgapped")
        cams = self.registry.get("weather-cams", "airgapped")
        ndmc = self.registry.get("weather-saudi-ndmc", "airgapped")

        om_forecast = openmeteo.fetch_forecast(location, days=2)
        om_norm = openmeteo.normalize(om_forecast)["observations"]
        owm_current = owm.normalize(owm.fetch_current(location))
        owm_alerts = owm.normalize(owm.fetch_alerts(location))
        cams_dust = cams.fetch_dust_forecast(location, hours=24)
        cams_norm = cams.normalize(cams_dust)["observations"]
        ndmc_alerts = ndmc.fetch_alerts()["alerts"]

        ndmc_metar = None
        if location in ndmc.config.saudi_airports:
            try:
                ndmc_metar = ndmc.normalize(ndmc.fetch_metar(location))
            except Exception:
                ndmc_metar = None
        if ndmc_metar is None and location == "riyadh":
            ndmc_metar = ndmc.normalize(ndmc.fetch_metar("OERK"))

        merged_current = ndmc_metar or om_norm[0] or owm_current
        forecast_24h = om_norm[:24]

        dust_now = {
            "aod": float(cams_dust.get("dust_aod", [0.0])[0]) if cams_dust.get("dust_aod") else 0.0,
            "pm10": float(cams_dust.get("pm10", [0.0])[0]) if cams_dust.get("pm10") else 0.0,
            "risk_level": cams.normalizer.classify_dust_risk(float(cams_dust.get("dust_aod", [0.0])[0])) if cams_dust.get("dust_aod") else "clear",
            "source": "CAMS",
        }

        marine = openmeteo.fetch_marine_forecast("strait_of_hormuz", days=2)
        marine_rows = openmeteo.normalizer.normalize_marine(marine.get("hourly", {}), openmeteo.config.saudi_locations["strait_of_hormuz"])
        wave0 = marine_rows[0]["wave_height_m"] if marine_rows else None
        operations = self._compute_ops_status(merged_current, wave0)

        alerts = []
        alerts.extend([{"source": "NDMC", **a} for a in ndmc_alerts])
        alerts.extend([{"source": "OWM", **a} for a in owm_alerts])
        alerts.extend(openmeteo.normalizer.generate_operational_alerts(forecast_24h, self.thresholds))

        confidence = self._weighted_confidence(ndmc_metar, om_norm[0] if om_norm else None, owm_current, cams_norm[0] if cams_norm else None)

        return {
            "location": location,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current": merged_current,
            "forecast_24h": forecast_24h,
            "dust": dust_now,
            "operations": operations,
            "alerts": alerts,
            "confidence": confidence,
            "providers_used": ["weather-saudi-ndmc", "weather-openmeteo", "weather-owm", "weather-cams"],
        }

    def get_saudi_weather_picture(self) -> dict[str, Any]:
        openmeteo = self.registry.get("weather-openmeteo", "airgapped")
        results: dict[str, Any] = {}
        sandstorm_in_progress: list[str] = []
        heat_warnings: list[str] = []

        for key in openmeteo.config.saudi_locations.keys():
            op = self.get_operational_weather(key)
            results[key] = op
            if op["dust"]["risk_level"] in {"sandstorm", "severe_storm"}:
                sandstorm_in_progress.append(key)
            if any(a.get("type") == "heat" for a in op["alerts"]):
                heat_warnings.append(key)

        overall = "GO"
        if sandstorm_in_progress:
            overall = "NO-GO"
        elif heat_warnings:
            overall = "CAUTION"

        return {
            "locations": results,
            "sandstorm_in_progress": sandstorm_in_progress,
            "heat_warnings": heat_warnings,
            "overall_ops_status": overall,
        }

    def get_dust_forecast(self, hours: int = 72) -> dict[str, Any]:
        cams = self.registry.get("weather-cams", "airgapped")
        openmeteo = self.registry.get("weather-openmeteo", "airgapped")

        cams_all = cams.fetch_all_saudi_dust(hours)
        timeline = []
        for location_key, data in cams_all["locations"].items():
            for ts, aod in zip(data.get("timestamps", []), data.get("dust_aod", [])):
                timeline.append({"location": location_key, "timestamp": ts, "aod": float(aod)})

        timeline.sort(key=lambda x: x["timestamp"])
        severe_entries = [e for e in timeline if e["aod"] >= cams.config.dust_aod_thresholds["sandstorm"]]
        onset_time = severe_entries[0]["timestamp"] if severe_entries else None
        peak = max(timeline, key=lambda x: x["aod"], default=None)
        clearance_candidates = [e for e in timeline if onset_time and e["timestamp"] > onset_time and e["aod"] < cams.config.dust_aod_thresholds["moderate_dust"]]
        clearance_time = clearance_candidates[0]["timestamp"] if clearance_candidates else None

        affected_order = []
        seen = set()
        for e in severe_entries:
            if e["location"] not in seen:
                affected_order.append(e["location"])
                seen.add(e["location"])

        secondary = openmeteo.fetch_all_saudi_locations(days=max(1, min(7, hours // 24)))

        return {
            "timeline": timeline,
            "onset_time": onset_time,
            "peak_intensity": peak,
            "clearance_time": clearance_time,
            "affected_locations_in_order": affected_order,
            "secondary_openmeteo": secondary,
        }

    def get_maritime_weather(self, zone: str = "strait_of_hormuz") -> dict[str, Any]:
        openmeteo = self.registry.get("weather-openmeteo", "airgapped")
        marine = openmeteo.fetch_marine_forecast(zone, days=3)
        rows = openmeteo.normalizer.normalize_marine(marine.get("hourly", {}), openmeteo.config.saudi_locations[zone])
        max_wave = max((r["wave_height_m"] for r in rows), default=0.0)
        return {
            "zone": zone,
            "forecast": rows,
            "usv_ops": "GO" if max_wave <= self.thresholds["wave_max_usv_m"] else "NO-GO",
            "patrol_boat_ops": "GO" if max_wave <= self.thresholds["wave_max_patrol_boat_m"] else "NO-GO",
        }

    def generate_weather_briefing(self, location: str | None = None) -> str:
        target = location or "riyadh"
        payload = self.get_operational_weather(target)
        current = payload["current"]
        ops = payload["operations"]
        dust = payload["dust"]
        # Tactical context: concise briefing format for command updates when disconnected from LLM services.
        return (
            f"1) Current conditions: T={getattr(current, 'temperature_c', 'N/A')}C, "
            f"wind={round(getattr(current, 'wind_speed_mps', 0.0)*3.6,1)}km/h, "
            f"visibility={round(getattr(current, 'visibility_km', 0.0),1)}km.\n"
            f"2) Forecast period (24h): {len(payload['forecast_24h'])} points analyzed.\n"
            f"3) Operational impact: Flight={ops['flight']}, Ground={ops['ground']}, UAV={ops['uav']}, Maritime={ops['maritime']}.\n"
            f"4) Recommended actions: Dust risk={dust['risk_level']} (AOD={dust['aod']:.2f}); prioritize equipment covers and route deconfliction."
        )

    def feed_to_navigation(self, location: str) -> dict[str, Any]:
        payload = self.get_operational_weather(location)
        current = payload["current"]
        wind_speed = float(getattr(current, "wind_speed_mps", 0.0) or 0.0)
        wind_dir = float(getattr(current, "wind_direction_deg", 0.0) or 0.0)
        visibility_m = float(getattr(current, "visibility_km", 0.0) or 0.0) * 1000.0
        dust_risk = payload["dust"]["risk_level"]
        altitude_adjust = 0
        if dust_risk in {"sandstorm", "severe_storm"}:
            altitude_adjust = 300
        elif dust_risk in {"heavy_dust", "moderate_dust"}:
            altitude_adjust = 100
        return {
            "wind_vector": {"speed_mps": wind_speed, "direction_deg": wind_dir},
            "visibility_m": visibility_m,
            "dust_risk": dust_risk,
            "recommended_altitude_adjustment": altitude_adjust,
        }

    def feed_to_maintenance(self, location: str) -> dict[str, Any]:
        payload = self.get_operational_weather(location)
        forecast = payload["forecast_24h"]
        dust_exposure = sum(1 for o in forecast if float(getattr(o, "dust_concentration", 0.0) or 0.0) >= self.thresholds["dust_sandstorm_threshold_ugm3"])
        heat_exposure = sum(1 for o in forecast if float(getattr(o, "temperature_c", 0.0) or 0.0) >= self.thresholds["temperature_max_operations_c"])
        actions = []
        if dust_exposure:
            actions.append("Inspect and replace air filters; apply sensor lens cleaning cycle.")
        if heat_exposure:
            actions.append("Advance cooling-system inspection and lubricant thermal check.")
        if not actions:
            actions.append("Continue standard maintenance interval.")
        return {
            "dust_exposure_hours": dust_exposure,
            "heat_exposure_hours": heat_exposure,
            "recommended_maintenance_actions": actions,
        }

    def health_check(self) -> dict[str, Any]:
        providers = {
            pid: self.registry.get(pid, "airgapped").health_check()
            for pid in ["weather-openmeteo", "weather-owm", "weather-cams", "weather-saudi-ndmc"]
        }
        return {"status": "ok", "providers": providers}
