"""Tests for tactical radar manager ingestion and fusion bridge."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.radar.models import RadarBand, RadarConfig, RadarType
from services.radar.radar_manager import RadarManager


def _config(radar_id: str = "radar-1") -> RadarConfig:
    return RadarConfig(
        radar_id=radar_id,
        radar_type=RadarType.GENERIC_3D,
        band=RadarBand.S,
        max_range_m=120_000.0,
        name_en="Test Tactical Radar",
        position_m=(100.0, 200.0, 5.0),
        clutter_snr_threshold_db=3.0,
    )


def test_register_and_list_radar() -> None:
    manager = RadarManager()
    config = _config()
    manager.register_radar(config)

    assert manager.get_radar(config.radar_id) == config
    assert len(manager.list_radars()) == 1
    sensor_ids = {sensor["sensor_id"] for sensor in manager.sensor_manager.get_sensors()}
    assert config.radar_id in sensor_ids


def test_ingest_scan_updates_status_and_bridges_to_sensor_manager() -> None:
    manager = RadarManager()
    manager.register_radar(_config())

    raw_data = {
        "plots": [
            {
                "plot_id": "p-001",
                "range_m": 10_000.0,
                "azimuth_deg": 15.0,
                "elevation_deg": 2.5,
                "snr_db": 18.0,
                "rcs_dbsm": -3.0,
                "radial_velocity_mps": 120.0,
            },
            {
                "plot_id": "p-002",
                "range_m": 5_000.0,
                "azimuth_deg": 25.0,
                "elevation_deg": 0.0,
                "snr_db": 1.0,  # should be filtered as clutter
                "rcs_dbsm": -25.0,
                "radial_velocity_mps": 10.0,
            },
        ]
    }

    plots = manager.ingest_scan("radar-1", raw_data)
    assert len(plots) == 1
    assert plots[0].position_cartesian is not None
    assert plots[0].correlated_track_id is not None

    status = manager.get_status("radar-1")
    assert status is not None
    assert status.scans_received == 1
    assert status.plots_received == 1
    assert status.plots_correlated == 1

    health = manager.sensor_manager.health_check()
    assert health["pending_readings"] == 1

    tracks = manager.process_fused_tracks()
    assert len(tracks) == 1


def test_ingest_scan_requires_registered_radar() -> None:
    manager = RadarManager()
    with pytest.raises(ValueError, match="not registered"):
        manager.ingest_scan("missing-radar", {"plots": []})


def test_correlation_persists_ids_and_stats() -> None:
    manager = RadarManager()
    manager.register_radar(_config())

    first = manager.ingest_scan(
        "radar-1",
        {
            "plots": [
                {
                    "plot_id": "a",
                    "range_m": 20_000.0,
                    "azimuth_deg": 90.0,
                    "elevation_deg": 0.0,
                    "snr_db": 10.0,
                }
            ]
        },
    )
    second = manager.ingest_scan(
        "radar-1",
        {
            "plots": [
                {
                    "plot_id": "b",
                    "range_m": 20_050.0,
                    "azimuth_deg": 90.0,
                    "elevation_deg": 0.0,
                    "snr_db": 11.0,
                }
            ]
        },
    )

    assert first[0].correlated_track_id is not None
    assert second[0].correlated_track_id == first[0].correlated_track_id

    all_status = manager.get_all_status()
    assert all_status["radar-1"]["scans"] == 2

    stats = manager.get_stats()
    assert stats["registered_radars"] == 1
    assert stats["total_scans"] == 2
    assert stats["total_plots"] == 2
    assert stats["active_correlations"] == 1

