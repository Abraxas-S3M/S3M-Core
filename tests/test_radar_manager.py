"""Unit tests for radar manager registration behavior."""

from __future__ import annotations

import pytest

from services.radar.models import RadarBand, RadarConfig, RadarType, ScanMode
from services.radar.radar_manager import RadarManager


def _sample_config(radar_id: str) -> RadarConfig:
    return RadarConfig(
        radar_id=radar_id,
        name_en=f"Radar {radar_id}",
        name_ar=f"Radar {radar_id}",
        radar_type=RadarType.RPS_82,
        band=RadarBand.X_BAND,
        scan_mode=ScanMode.ROTATING,
        position=(0.0, 0.0, 0.0),
        max_range_m=10_000.0,
        scan_rate_rpm=12.0,
    )


def test_register_radar_tracks_insertion_order() -> None:
    """Order preservation supports deterministic tactical playback."""
    manager = RadarManager()
    first = manager.register_radar(_sample_config("r1"))
    second = manager.register_radar(_sample_config("r2"))

    assert manager.list_radars() == [first, second]
    assert manager.get_radar("r1") is first
    assert manager.get_radar("missing") is None


def test_register_radar_rejects_duplicate_id() -> None:
    """Duplicate IDs are blocked to prevent ambiguous C3 sensor references."""
    manager = RadarManager()
    manager.register_radar(_sample_config("dupe"))

    with pytest.raises(ValueError, match="already registered"):
        manager.register_radar(_sample_config("dupe"))
