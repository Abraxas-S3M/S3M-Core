from __future__ import annotations

from datetime import timezone

import pytest

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode


def test_parse_single_payload_with_field_fallbacks() -> None:
    adapter = Generic3DRadarAdapter()
    plots = adapter.parse_raw_data(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "range_km": 12.5,
            "bearing_deg": 275.0,
            "velocity_mps": -40.0,
            "snr_db": 22.1,
        }
    )

    assert len(plots) == 1
    assert plots[0].range_m == pytest.approx(12_500.0)
    assert plots[0].azimuth_deg == pytest.approx(275.0)
    assert plots[0].radial_velocity_mps == pytest.approx(-40.0)
    assert plots[0].snr_db == pytest.approx(22.1)
    assert plots[0].timestamp.tzinfo == timezone.utc


def test_parse_plots_list_and_defaults() -> None:
    adapter = Generic3DRadarAdapter()
    plots = adapter.parse_raw_data(
        {
            "plots": [
                {"range_m": 1200, "azimuth_deg": 5.0, "elevation_deg": 1.0},
                {"range_km": 3.0, "bearing_deg": 15.0, "radial_velocity_mps": 12.0},
            ]
        }
    )

    assert len(plots) == 2
    assert plots[0].range_m == pytest.approx(1200.0)
    assert plots[1].range_m == pytest.approx(3000.0)
    assert plots[1].azimuth_deg == pytest.approx(15.0)
    assert plots[1].snr_db == pytest.approx(18.0)


def test_parse_rejects_invalid_payload_shapes() -> None:
    adapter = Generic3DRadarAdapter()
    with pytest.raises(ValueError, match="raw_data must be a dictionary"):
        adapter.parse_raw_data([])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="plots must be a list"):
        adapter.parse_raw_data({"plots": {"range_m": 1000}})

    with pytest.raises(ValueError, match="plot at index 0 must be a dictionary"):
        adapter.parse_raw_data({"plots": ["not-a-dict"]})


def test_default_config_matches_generic_3d_baseline() -> None:
    adapter = Generic3DRadarAdapter()
    cfg = adapter.create_default_config()

    assert cfg.radar_type is RadarType.GENERIC_3D
    assert cfg.band is RadarBand.S_BAND
    assert cfg.scan_mode is ScanMode.ROTATING
    assert cfg.max_range_m == pytest.approx(60_000.0)
    assert cfg.has_elevation is True
    assert cfg.has_doppler is True


def test_models_enforce_basic_validation() -> None:
    cfg = RadarConfig(radar_id="alpha-radar")
    assert cfg.radar_id == "alpha-radar"

    with pytest.raises(ValueError, match="range_m must be non-negative"):
        RadarPlot(
            radar_id="r1",
            timestamp="2026-01-01T00:00:00Z",
            range_m=-1,
            azimuth_deg=0,
            elevation_deg=0,
            radial_velocity_mps=0,
            rcs_dbsm=0,
            snr_db=0,
            signal_strength=0,
        )
