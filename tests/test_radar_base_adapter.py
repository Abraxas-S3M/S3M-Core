"""Tests for tactical radar adapter plot filtering."""

from __future__ import annotations

from typing import Any, Dict, List

from services.radar.adapters.base_adapter import BaseRadarAdapter
from services.radar.models import RadarConfig, RadarPlot


class _StubRadarAdapter(BaseRadarAdapter):
    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        del raw_data
        return []

    def create_default_config(self) -> RadarConfig:
        return RadarConfig()


def test_validate_plot_rejects_out_of_range_and_low_snr() -> None:
    adapter = _StubRadarAdapter(
        RadarConfig(
            min_range_m=100.0,
            max_range_m=2_000.0,
            has_elevation=False,
            min_detectable_snr_db=6.0,
        )
    )
    assert adapter.validate_plot(RadarPlot(range_m=50.0, azimuth_deg=10.0, snr_db=20.0)) is False
    assert adapter.validate_plot(RadarPlot(range_m=500.0, azimuth_deg=10.0, snr_db=5.0)) is False


def test_validate_plot_checks_elevation_when_enabled() -> None:
    adapter = _StubRadarAdapter(
        RadarConfig(
            min_range_m=0.0,
            max_range_m=10_000.0,
            has_elevation=True,
            min_elevation_deg=-3.0,
            max_elevation_deg=30.0,
        )
    )
    assert adapter.validate_plot(RadarPlot(range_m=500.0, azimuth_deg=15.0, elevation_deg=-5.0, snr_db=10.0)) is False
    assert adapter.validate_plot(RadarPlot(range_m=500.0, azimuth_deg=15.0, elevation_deg=12.0, snr_db=10.0)) is True


def test_filter_clutter_keeps_only_valid_plots() -> None:
    adapter = _StubRadarAdapter(
        RadarConfig(min_range_m=100.0, max_range_m=500.0, has_elevation=False, min_detectable_snr_db=8.0)
    )
    plots = [
        RadarPlot(range_m=50.0, azimuth_deg=0.0, snr_db=20.0),
        RadarPlot(range_m=200.0, azimuth_deg=5.0, snr_db=4.0),
        RadarPlot(range_m=250.0, azimuth_deg=8.0, snr_db=10.0),
    ]
    filtered = adapter.filter_clutter(plots)
    assert filtered == [plots[2]]
