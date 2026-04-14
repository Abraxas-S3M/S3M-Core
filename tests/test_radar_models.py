"""Unit tests for radar data model validation."""

from __future__ import annotations

import pytest

from services.radar.models import RadarBand, RadarConfig, RadarType, ScanMode


def test_rotating_radar_requires_scan_rate() -> None:
    """Rotating tactical radars must declare sweep rate for track freshness."""
    with pytest.raises(ValueError, match="scan_rate_rpm is required"):
        RadarConfig(
            name_en="RPS-82",
            name_ar="RPS-82",
            radar_type=RadarType.RPS_82,
            band=RadarBand.X_BAND,
            scan_mode=ScanMode.ROTATING,
            position=(0.0, 0.0, 0.0),
            max_range_m=10_000,
        )


def test_electronic_radar_requires_update_rate() -> None:
    """Electronic arrays must define refresh rate for C3 track confidence."""
    with pytest.raises(ValueError, match="update_rate_hz is required"):
        RadarConfig(
            name_en="AESA",
            name_ar="AESA",
            radar_type=RadarType.AESA_WESTERN,
            band=RadarBand.C_BAND,
            scan_mode=ScanMode.ELECTRONIC,
            position=(0.0, 0.0, 0.0),
            max_range_m=15_000,
        )


def test_radar_config_accepts_valid_rotating_profile() -> None:
    """Valid rotating sensor profiles should instantiate for offline exercises."""
    cfg = RadarConfig(
        name_en="RPS-202",
        name_ar="RPS-202",
        radar_type=RadarType.RPS_202,
        band=RadarBand.S_BAND,
        scan_mode=ScanMode.ROTATING,
        position=(10.0, 20.0, 5.0),
        max_range_m=50_000,
        min_range_m=100.0,
        scan_rate_rpm=8.0,
    )

    assert cfg.name_en == "RPS-202"
    assert cfg.scan_rate_rpm == pytest.approx(8.0)
