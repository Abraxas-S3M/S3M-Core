from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.radar.adapters.generic_2d_radar import Generic2DRadarAdapter
from services.radar.models import RadarBand, RadarType, ScanMode


def test_parse_raw_data_handles_range_km_and_bearing_alias() -> None:
    adapter = Generic2DRadarAdapter()
    plots = adapter.parse_raw_data(
        {
            "plots": [
                {
                    "timestamp": "2026-04-14T10:30:00+00:00",
                    "range_km": 12.5,
                    "bearing_deg": 44.0,
                    "velocity_mps": 125.0,
                    "rcs_dbsm": 3.5,
                    "snr_db": 22.0,
                    "signal_strength": 0.88,
                }
            ]
        }
    )

    assert len(plots) == 1
    plot = plots[0]
    assert plot.range_m == 12_500.0
    assert plot.azimuth_deg == 44.0
    assert plot.elevation_deg == 0.0
    assert plot.radial_velocity_mps == 125.0
    assert plot.timestamp == datetime(2026, 4, 14, 10, 30, tzinfo=timezone.utc)


def test_parse_raw_data_accepts_single_plot_payload_and_defaults() -> None:
    adapter = Generic2DRadarAdapter()
    plots = adapter.parse_raw_data({"range_m": 1000.0, "azimuth_deg": 90.0})

    assert len(plots) == 1
    plot = plots[0]
    assert plot.range_m == 1000.0
    assert plot.azimuth_deg == 90.0
    assert plot.snr_db == 15.0
    assert plot.signal_strength == 0.0


def test_parse_raw_data_rejects_invalid_timestamp() -> None:
    adapter = Generic2DRadarAdapter()
    with pytest.raises(ValueError, match="Invalid timestamp format"):
        adapter.parse_raw_data({"plots": [{"timestamp": "not-a-timestamp"}]})


def test_create_default_config_is_2d_rotating_profile() -> None:
    adapter = Generic2DRadarAdapter()
    config = adapter.create_default_config()

    assert config.radar_type is RadarType.GENERIC_2D
    assert config.band is RadarBand.S_BAND
    assert config.scan_mode is ScanMode.ROTATING
    assert config.has_elevation is False
    assert config.has_doppler is False
