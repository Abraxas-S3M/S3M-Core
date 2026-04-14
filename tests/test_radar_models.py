"""Tests for tactical radar model validation."""

from __future__ import annotations

from datetime import datetime

import pytest

from services.radar.models import RadarConfig, RadarPlot, RadarScan


def test_radar_config_rejects_invalid_range_envelope() -> None:
    with pytest.raises(ValueError, match="max_range_m must be > min_range_m"):
        RadarConfig(min_range_m=2_000.0, max_range_m=1_000.0)


def test_radar_plot_rejects_negative_range() -> None:
    with pytest.raises(ValueError, match="range_m must be >= 0.0"):
        RadarPlot(range_m=-1.0, azimuth_deg=0.0)


def test_radar_scan_normalizes_naive_timestamp_to_utc() -> None:
    scan = RadarScan(
        radar_id="radar-1",
        timestamp=datetime(2026, 4, 14, 12, 0, 0),
        plots=[RadarPlot(range_m=1_500.0, azimuth_deg=25.0, snr_db=12.0)],
    )
    assert scan.timestamp.tzinfo is not None
