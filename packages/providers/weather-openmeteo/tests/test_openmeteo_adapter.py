from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.weather_openmeteo.adapter import OpenMeteoAdapter
from packages.providers.weather_openmeteo.config import SAUDI_LOCATIONS
from packages.providers.weather_openmeteo.normalizer import OpenMeteoNormalizer


def test_manifest_correct() -> None:
    manifest = OpenMeteoAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "weather-openmeteo"
    assert manifest.category == "WEATHER_ENVIRONMENT"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "none"


def test_no_auth_required() -> None:
    assert OpenMeteoAdapter(mode="airgapped").validate_credentials() is True


def test_saudi_locations_defined() -> None:
    assert len(SAUDI_LOCATIONS) == 12
    for loc in SAUDI_LOCATIONS.values():
        assert "lat" in loc and "lon" in loc


def test_wind_speed_conversion() -> None:
    n = OpenMeteoNormalizer()
    obs = n.normalize_hourly(
        {
            "time": ["2026-04-01T00:00"],
            "temperature_2m": [40],
            "relative_humidity_2m": [10],
            "wind_speed_10m": [36],
            "wind_direction_10m": [180],
            "visibility": [10000],
            "precipitation": [0],
            "cloud_cover": [0],
            "uv_index": [1],
            "dust": [20],
            "surface_pressure": [1008],
        },
        SAUDI_LOCATIONS["riyadh"],
    )[0]
    assert round(obs.wind_speed_mps, 2) == 10.00


def test_visibility_conversion() -> None:
    n = OpenMeteoNormalizer()
    obs = n.normalize_hourly(
        {
            "time": ["2026-04-01T00:00"],
            "temperature_2m": [40],
            "relative_humidity_2m": [10],
            "wind_speed_10m": [20],
            "wind_direction_10m": [180],
            "visibility": [24140],
            "precipitation": [0],
            "cloud_cover": [0],
            "uv_index": [1],
            "dust": [20],
            "surface_pressure": [1008],
        },
        SAUDI_LOCATIONS["riyadh"],
    )[0]
    assert round(obs.visibility_km, 2) == 24.14


def test_dust_concentration_populated() -> None:
    obs = OpenMeteoAdapter(mode="airgapped").normalize(OpenMeteoAdapter(mode="airgapped").fetch_forecast("riyadh", 1))["observations"][0]
    assert obs.dust_concentration is not None


def test_sandstorm_alert_generated() -> None:
    adapter = OpenMeteoAdapter(mode="airgapped")
    observations = adapter.normalize(adapter.fetch_forecast("riyadh", 3))["observations"]
    alerts = adapter.normalizer.generate_operational_alerts(observations, adapter.config.operational_thresholds)
    assert any(a["type"] == "sandstorm" and a["severity"] == "critical" for a in alerts)


def test_heat_alert_generated() -> None:
    n = OpenMeteoNormalizer()
    obs = n.normalize_hourly(
        {
            "time": ["2026-04-01T00:00"],
            "temperature_2m": [53],
            "relative_humidity_2m": [8],
            "wind_speed_10m": [20],
            "wind_direction_10m": [180],
            "visibility": [10000],
            "precipitation": [0],
            "cloud_cover": [0],
            "uv_index": [1],
            "dust": [20],
            "surface_pressure": [1008],
        },
        SAUDI_LOCATIONS["riyadh"],
    )
    alerts = n.generate_operational_alerts(obs, OpenMeteoAdapter(mode="airgapped").config.operational_thresholds)
    assert any(a["type"] == "heat" and a["severity"] == "critical" for a in alerts)


def test_visibility_flight_nogo() -> None:
    n = OpenMeteoNormalizer()
    obs = n.normalize_hourly(
        {
            "time": ["2026-04-01T00:00"],
            "temperature_2m": [40],
            "relative_humidity_2m": [8],
            "wind_speed_10m": [20],
            "wind_direction_10m": [180],
            "visibility": [800],
            "precipitation": [0],
            "cloud_cover": [0],
            "uv_index": [1],
            "dust": [20],
            "surface_pressure": [1008],
        },
        SAUDI_LOCATIONS["riyadh"],
    )
    alerts = n.generate_operational_alerts(obs, OpenMeteoAdapter(mode="airgapped").config.operational_thresholds)
    assert any(a["type"] == "visibility" for a in alerts)


def test_uav_wind_nogo() -> None:
    n = OpenMeteoNormalizer()
    obs = n.normalize_hourly(
        {
            "time": ["2026-04-01T00:00"],
            "temperature_2m": [40],
            "relative_humidity_2m": [8],
            "wind_speed_10m": [45],
            "wind_direction_10m": [180],
            "visibility": [10000],
            "precipitation": [0],
            "cloud_cover": [0],
            "uv_index": [1],
            "dust": [20],
            "surface_pressure": [1008],
        },
        SAUDI_LOCATIONS["riyadh"],
    )
    alerts = n.generate_operational_alerts(obs, OpenMeteoAdapter(mode="airgapped").config.operational_thresholds)
    assert any(a["type"] == "wind" for a in alerts)


def test_maritime_sea_state_go() -> None:
    n = OpenMeteoNormalizer()
    marine = n.normalize_marine(
        {
            "time": ["2026-04-01T00:00", "2026-04-01T01:00"],
            "wave_height": [1.5, 3.0],
            "wave_period": [5, 6],
            "wave_direction": [90, 95],
            "swell_wave_height": [1.0, 2.0],
            "ocean_current_velocity": [0.5, 0.6],
        },
        SAUDI_LOCATIONS["strait_of_hormuz"],
    )
    assert marine[0]["sea_state_go"] is True
    assert marine[1]["sea_state_go"] is False


def test_confidence_decay_by_forecast_hour() -> None:
    n = OpenMeteoNormalizer()
    assert n._confidence_for_hour(0) == 0.95
    assert n._confidence_for_hour(48) == 0.85
    assert n._confidence_for_hour(96) == 0.70


def test_operational_conditions_structure() -> None:
    data = OpenMeteoAdapter(mode="airgapped").check_operational_conditions("riyadh")
    assert {"flight_ops", "ground_ops", "uav_ops", "maritime_ops"}.issubset(data.keys())


def test_fetch_airgapped() -> None:
    data = OpenMeteoAdapter(mode="airgapped").fetch_forecast("riyadh", 3)
    assert "hourly" in data and "daily" in data
