from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.weather_owm.adapter import OpenWeatherMapAdapter


def test_manifest_correct() -> None:
    manifest = OpenWeatherMapAdapter(mode="airgapped").get_manifest()
    assert manifest.tier == "FREEMIUM"
    assert manifest.auth_type == "api_key"


def test_wind_speed_already_mps() -> None:
    obs = OpenWeatherMapAdapter(mode="airgapped").normalize(OpenWeatherMapAdapter(mode="airgapped").fetch_current("riyadh"))
    assert abs(obs.wind_speed_mps - 4.5) < 0.001


def test_visibility_conversion() -> None:
    obs = OpenWeatherMapAdapter(mode="airgapped").normalize(OpenWeatherMapAdapter(mode="airgapped").fetch_current("riyadh"))
    assert obs.visibility_km == 10.0


def test_aqi_label_mapping() -> None:
    adapter = OpenWeatherMapAdapter(mode="airgapped")
    aq = adapter.normalize(adapter.fetch_air_quality("riyadh"))
    assert aq["aqi_label"] == "moderate"
    assert adapter.config.aqi_levels[5] == "very_poor"


def test_pm10_as_dust_proxy() -> None:
    adapter = OpenWeatherMapAdapter(mode="airgapped")
    aq = adapter.normalize(adapter.fetch_air_quality("riyadh"))
    assert aq["dust_proxy"] == aq["pm10"]


def test_normalize_current_all_fields() -> None:
    obs = OpenWeatherMapAdapter(mode="airgapped").normalize(OpenWeatherMapAdapter(mode="airgapped").fetch_current("riyadh"))
    assert obs.temperature_c > 0
    assert obs.humidity_pct >= 0
    assert obs.wind_speed_mps >= 0
    assert obs.visibility_km >= 0


def test_normalize_forecast_count() -> None:
    adapter = OpenWeatherMapAdapter(mode="airgapped")
    obs = adapter.normalize(adapter.fetch_forecast("riyadh"))
    assert len(obs) == 40


def test_alert_normalization() -> None:
    adapter = OpenWeatherMapAdapter(mode="airgapped")
    alerts = adapter.normalize(adapter.fetch_alerts("riyadh"))
    assert alerts and {"event", "severity", "valid_from", "valid_until"}.issubset(alerts[0].keys())


def test_fetch_airgapped() -> None:
    assert "main" in OpenWeatherMapAdapter(mode="airgapped").fetch_current("riyadh")
