"""Tests for localization manager source orchestration."""

from __future__ import annotations

from src.navigation.localization.localization_manager import LocalizationManager
from src.navigation.models import NavState


def test_initialization_creates_components():
    manager = LocalizationManager()
    assert manager.pose_estimator is not None
    assert manager.vins_adapter is not None
    assert manager.lidar_adapter is not None
    assert manager.dead_reckoning is not None
    assert manager.gps_monitor is not None


def test_update_with_gps_data_produces_gps_fused_mode():
    manager = LocalizationManager()
    state = manager.update(
        gps_data={"satellites": 10, "hdop": 1.2, "fix_type": "3d", "position": (5.0, 6.0, 1.0)},
        imu_data={"linear_accel": (0.0, 0.0, 0.0), "angular_vel": (0.0, 0.0, 0.0), "dt": 0.05},
    )
    assert isinstance(state, NavState)
    assert state.localization_mode == "gps_fused"


def test_update_without_gps_and_vio_falls_back_dead_reckoning():
    manager = LocalizationManager()
    state = manager.update(imu_data={"linear_accel": (0.0, 0.0, 0.0), "angular_vel": (0.0, 0.0, 0.0), "dt": 0.1})
    assert state.localization_mode == "dead_reckoning"


def test_get_state_returns_navstate():
    manager = LocalizationManager()
    manager.update(imu_data={"linear_accel": (0.0, 0.0, 0.0), "angular_vel": (0.0, 0.0, 0.0), "dt": 0.1})
    state = manager.get_state()
    assert isinstance(state, NavState)
    assert state.localization_mode in {"gps_fused", "visual_inertial", "lidar_inertial", "dead_reckoning"}


def test_health_check_reports_sources():
    manager = LocalizationManager()
    manager.update(imu_data={"linear_accel": (0.0, 0.0, 0.0), "angular_vel": (0.0, 0.0, 0.0), "dt": 0.1})
    health = manager.health_check()
    assert "sources" in health
    assert "gps" in health["sources"]
    assert "vins" in health["sources"]
    assert "lidar_odom" in health["sources"]
    assert "dead_reckoning" in health["sources"]
