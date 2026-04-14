"""Unit tests for the RPS-202 radar adapter parsing contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.radar.adapters.rps202_adapter import RPS202Adapter
from services.radar.models import RadarBand, RadarType, ScanMode


def test_parse_single_plot_with_range_km_and_bearing() -> None:
    adapter = RPS202Adapter()
    plots = adapter.parse_raw_data(
        {
            "timestamp": "2026-04-14T00:00:00Z",
            "range_km": 12.5,
            "bearing_deg": 35.0,
            "elevation_deg": 4.0,
            "velocity_mps": 150.0,
            "rcs_dbsm": -2.5,
            "snr_db": 21.0,
        }
    )

    assert len(plots) == 1
    plot = plots[0]
    assert plot.radar_id == "rps202-c3-van"
    assert plot.timestamp == datetime(2026, 4, 14, tzinfo=timezone.utc)
    assert plot.range_m == pytest.approx(12_500.0)
    assert plot.azimuth_deg == pytest.approx(35.0)
    assert plot.elevation_deg == pytest.approx(4.0)
    assert plot.radial_velocity_mps == pytest.approx(150.0)
    assert plot.rcs_dbsm == pytest.approx(-2.5)
    assert plot.snr_db == pytest.approx(21.0)


def test_parse_plots_list_and_default_fields() -> None:
    adapter = RPS202Adapter()
    now_before = datetime.now(timezone.utc)
    plots = adapter.parse_raw_data(
        {
            "plots": [
                {"range_m": 1000.0, "azimuth_deg": 10.0},
                {"range_km": 2.0, "bearing_deg": 90.0, "snr_db": 12.0},
            ]
        }
    )
    now_after = datetime.now(timezone.utc)

    assert len(plots) == 2
    assert plots[0].range_m == pytest.approx(1000.0)
    assert plots[0].azimuth_deg == pytest.approx(10.0)
    assert now_before - timedelta(seconds=1) <= plots[0].timestamp <= now_after + timedelta(seconds=1)
    assert plots[1].range_m == pytest.approx(2000.0)
    assert plots[1].azimuth_deg == pytest.approx(90.0)
    assert plots[1].snr_db == pytest.approx(12.0)
    assert plots[1].radial_velocity_mps == pytest.approx(0.0)


def test_parse_rejects_invalid_payload_shapes() -> None:
    adapter = RPS202Adapter()
    with pytest.raises(ValueError, match="raw_data must be a dictionary payload"):
        adapter.parse_raw_data([])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="plots field must be a list"):
        adapter.parse_raw_data({"plots": "invalid"})  # type: ignore[dict-item]

    with pytest.raises(ValueError, match="plot entry at index 0 must be a dictionary"):
        adapter.parse_raw_data({"plots": [123]})  # type: ignore[list-item]


def test_parse_rejects_invalid_numeric_and_range_values() -> None:
    adapter = RPS202Adapter()
    with pytest.raises(ValueError, match="finite number"):
        adapter.parse_raw_data({"range_m": "not-a-number"})

    with pytest.raises(ValueError, match="range must be non-negative"):
        adapter.parse_raw_data({"range_m": -1.0})


def test_create_default_config_values() -> None:
    adapter = RPS202Adapter()
    config = adapter.create_default_config()
    assert config.radar_id == "rps202-c3-van"
    assert config.radar_type is RadarType.RPS_202
    assert config.band is RadarBand.S_BAND
    assert config.scan_mode is ScanMode.ROTATING
    assert config.max_range_m == pytest.approx(50_000.0)
