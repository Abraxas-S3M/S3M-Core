"""Unit tests for Krechet radar suite template construction."""

from __future__ import annotations

import pytest

from services.radar import RadarManager, RadarType, ScanMode, create_krechet_radar_suite


def test_create_krechet_radar_suite_registers_expected_profiles() -> None:
    """Template should deploy the three-radar reconnaissance package."""
    manager = RadarManager()
    center = (100.0, 200.0, 10.0)

    configs = create_krechet_radar_suite(manager=manager, center=center)

    assert len(configs) == 3
    assert manager.list_radars() == configs
    assert [cfg.radar_type for cfg in configs] == [
        RadarType.RPS_82,
        RadarType.RPS_202,
        RadarType.AESA_WESTERN,
    ]
    assert configs[0].position == pytest.approx((1100.0, 2200.0, 10.0))
    assert configs[1].position == pytest.approx((100.0, 200.0, 15.0))
    assert configs[2].position == pytest.approx((-400.0, 700.0, 18.0))
    assert configs[2].scan_mode is ScanMode.ELECTRONIC
    assert configs[2].update_rate_hz == pytest.approx(2.0)


def test_create_krechet_radar_suite_validates_center() -> None:
    """Invalid centers are rejected to keep offline simulations deterministic."""
    manager = RadarManager()

    with pytest.raises(ValueError, match="exactly three coordinates"):
        create_krechet_radar_suite(manager=manager, center=(1.0, 2.0))
