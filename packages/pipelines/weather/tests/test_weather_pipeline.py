from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.pipelines.weather.weather_pipeline import WeatherOperationsPipeline


def test_operational_weather_merged() -> None:
    data = WeatherOperationsPipeline().get_operational_weather("riyadh")
    assert len(data["providers_used"]) == 4
    assert data["current"].provenance.provider_id in {"weather-saudi-ndmc", "weather-openmeteo", "weather-owm"}


def test_operations_go_nogo() -> None:
    p = WeatherOperationsPipeline()
    clear = p._compute_ops_status(type("Obj", (), {"visibility_km": 10, "wind_speed_mps": 4, "dust_concentration": 20})(), 1.0)
    storm = p._compute_ops_status(type("Obj", (), {"visibility_km": 0.2, "wind_speed_mps": 20, "dust_concentration": 650})(), 5.0)
    assert all(v == "GO" for v in clear.values())
    assert all(v == "NO-GO" for v in storm.values())


def test_dust_forecast_timeline() -> None:
    data = WeatherOperationsPipeline().get_dust_forecast(72)
    assert "onset_time" in data and "peak_intensity" in data and "clearance_time" in data


def test_saudi_weather_picture_all_locations() -> None:
    pic = WeatherOperationsPipeline().get_saudi_weather_picture()
    assert len(pic["locations"]) == 12


def test_sandstorm_locations_flagged() -> None:
    pic = WeatherOperationsPipeline().get_saudi_weather_picture()
    assert isinstance(pic["sandstorm_in_progress"], list)


def test_maritime_weather_sea_state() -> None:
    data = WeatherOperationsPipeline().get_maritime_weather("strait_of_hormuz")
    assert {"usv_ops", "patrol_boat_ops"}.issubset(data.keys())


def test_feed_to_navigation_structure() -> None:
    data = WeatherOperationsPipeline().feed_to_navigation("riyadh")
    assert {"wind_vector", "visibility_m", "dust_risk", "recommended_altitude_adjustment"}.issubset(data.keys())


def test_feed_to_maintenance_structure() -> None:
    data = WeatherOperationsPipeline().feed_to_maintenance("riyadh")
    assert {"dust_exposure_hours", "heat_exposure_hours", "recommended_maintenance_actions"}.issubset(data.keys())


def test_confidence_ndmc_highest() -> None:
    p = WeatherOperationsPipeline()
    fake = type("Obj", (), {"provenance": type("Prov", (), {"confidence": 1.0})()})
    low = type("Obj", (), {"provenance": type("Prov", (), {"confidence": 0.1})()})
    conf = p._weighted_confidence(fake, low, low, low)
    assert conf > 0.4


def test_health_check_all_providers() -> None:
    health = WeatherOperationsPipeline().health_check()
    assert set(health["providers"].keys()) == {"weather-openmeteo", "weather-owm", "weather-cams", "weather-saudi-ndmc"}
