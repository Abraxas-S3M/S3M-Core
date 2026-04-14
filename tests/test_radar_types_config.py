"""Unit tests for radar type library configuration."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_radar_types_config_has_expected_schema_and_values() -> None:
    config_path = Path("configs/radar/radar_types.yaml")
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    radar_types = config_data.get("radar_types")
    assert isinstance(radar_types, dict)
    assert len(radar_types) == 4

    allowed_bands = {"L", "S", "C", "X", "Ku"}
    for radar_id, radar in radar_types.items():
        assert isinstance(radar_id, str) and radar_id
        assert isinstance(radar.get("name_en"), str) and radar["name_en"]
        assert isinstance(radar.get("name_ar"), str) and radar["name_ar"]
        assert radar.get("band") in allowed_bands
        assert radar.get("scan_mode") in {"rotating", "electronic"}
        assert isinstance(radar.get("role"), str) and radar["role"]

        min_range_m = radar.get("min_range_m")
        max_range_m = radar.get("max_range_m")
        assert isinstance(min_range_m, (int, float)) and min_range_m >= 0
        assert isinstance(max_range_m, (int, float)) and max_range_m > min_range_m

        assert isinstance(radar.get("has_elevation"), bool)
        assert isinstance(radar.get("has_doppler"), bool)

        range_noise_std_m = radar.get("range_noise_std_m")
        azimuth_noise_std_deg = radar.get("azimuth_noise_std_deg")
        assert isinstance(range_noise_std_m, (int, float)) and range_noise_std_m >= 0
        assert isinstance(azimuth_noise_std_deg, (int, float)) and azimuth_noise_std_deg >= 0

        if radar["has_elevation"]:
            elevation_noise_std_deg = radar.get("elevation_noise_std_deg")
            assert isinstance(elevation_noise_std_deg, (int, float)) and elevation_noise_std_deg >= 0

        if radar["scan_mode"] == "rotating":
            # Tactical timing context: rotating sensors need positive sweep cadence.
            scan_rate_rpm = radar.get("scan_rate_rpm")
            assert isinstance(scan_rate_rpm, (int, float)) and scan_rate_rpm > 0
        else:
            # Tactical timing context: electronic scan sensors expose revisit rate.
            update_rate_hz = radar.get("update_rate_hz")
            assert isinstance(update_rate_hz, (int, float)) and update_rate_hz > 0

        min_detectable_rcs_dbsm = radar.get("min_detectable_rcs_dbsm")
        if min_detectable_rcs_dbsm is not None:
            assert isinstance(min_detectable_rcs_dbsm, (int, float))
