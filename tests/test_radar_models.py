"""Unit tests for radar adapter data models.

Military context:
These tests verify radar plot normalization, scan timing semantics, and
configuration guardrails that protect tactical sensor ingestion pipelines.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.radar.models import (
    RCSClassification,
    RadarBand,
    RadarConfig,
    RadarPlot,
    RadarScan,
    RadarStatus,
    RadarType,
    ScanMode,
)


def test_radar_plot_rejects_negative_range():
    with pytest.raises(ValueError, match="range_m must be non-negative"):
        RadarPlot(range_m=-1.0)


def test_radar_plot_normalizes_azimuth_and_serializes():
    plot = RadarPlot(
        radar_id="radar-1",
        timestamp=datetime(2026, 4, 14, 8, 0, tzinfo=timezone.utc),
        range_m=12_500.0,
        azimuth_deg=725.123,
        elevation_deg=5.4321,
        radial_velocity_mps=-45.678,
        rcs_dbsm=-10.55,
        snr_db=18.1234,
        position_cartesian=(1.1, 2.2, 3.3),
        rcs_classification=RCSClassification.MEDIUM_UAV,
        classification_confidence=0.87654,
        correlated_track_id="trk-44",
    )

    payload = plot.to_dict()
    assert plot.azimuth_deg == pytest.approx(5.123)
    assert payload["azimuth_deg"] == 5.12
    assert payload["position_cartesian"] == [1.1, 2.2, 3.3]
    assert payload["rcs_classification"] == "medium_uav"
    assert payload["classification_confidence"] == 0.877


def test_radar_plot_rcs_linear_conversion():
    plot = RadarPlot(rcs_dbsm=10.0)
    assert plot.rcs_linear_m2 == pytest.approx(10.0)


def test_radar_scan_plot_count_matches_plot_list():
    scan = RadarScan(plots=[RadarPlot(), RadarPlot(), RadarPlot()])
    assert scan.plot_count == 3


def test_radar_config_validates_range_limits():
    with pytest.raises(ValueError, match="max_range_m must exceed min_range_m"):
        RadarConfig(max_range_m=500.0, min_range_m=500.0)


def test_radar_config_scan_period_prefers_scan_rate():
    cfg = RadarConfig(scan_rate_rpm=12.0, update_rate_hz=9.0)
    assert cfg.scan_period_s == pytest.approx(5.0)


def test_radar_config_scan_period_uses_update_rate_when_needed():
    cfg = RadarConfig(scan_rate_rpm=0.0, update_rate_hz=2.0)
    assert cfg.scan_period_s == pytest.approx(0.5)


def test_radar_config_scan_period_fallback_default():
    cfg = RadarConfig(scan_rate_rpm=0.0, update_rate_hz=0.0)
    assert cfg.scan_period_s == pytest.approx(10.0)


def test_radar_config_to_dict_serializes_enums_and_position():
    cfg = RadarConfig(
        radar_id="radar-9",
        name_en="Krechet Unit 9",
        name_ar="كريشت 9",
        radar_type=RadarType.AESA_WESTERN,
        band=RadarBand.S_BAND,
        scan_mode=ScanMode.ELECTRONIC,
        position=(24.2, 46.7, 500.0),
        max_range_m=120_000.0,
        has_elevation=True,
        has_doppler=True,
        scan_rate_rpm=0.0,
        update_rate_hz=4.0,
        operational=False,
    )
    payload = cfg.to_dict()
    assert payload["radar_type"] == "aesa_western"
    assert payload["band"] == "S"
    assert payload["scan_mode"] == "electronic"
    assert payload["position"] == [24.2, 46.7, 500.0]
    assert payload["scan_period_s"] == 0.25


def test_radar_status_default_state():
    status = RadarStatus()
    assert status.operational is True
    assert status.scans_received == 0
