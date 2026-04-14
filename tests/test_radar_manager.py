"""Unit tests for tactical radar ingestion and track fusion."""

from __future__ import annotations

import pytest

from services.radar import RadarManager, TrackState, create_krechet_radar_suite


def test_krechet_suite_fuses_layered_detections_into_confirmed_track() -> None:
    """Layered radars should produce one corroborated tactical air track."""
    manager = RadarManager()
    configs = create_krechet_radar_suite(manager, center=(0.0, 0.0, 0.0))
    assert len(configs) == 3

    manager.ingest_scan(
        configs[2].radar_id,
        {
            "plots": [
                {
                    "range_m": 45000,
                    "azimuth_deg": 10,
                    "elevation_deg": 2,
                    "velocity_mps": 55,
                    "rcs_dbsm": -10,
                    "snr_db": 22,
                }
            ]
        },
    )
    manager.ingest_scan(
        configs[1].radar_id,
        {
            "plots": [
                {
                    "range_m": 18000,
                    "azimuth_deg": 12,
                    "elevation_deg": 3,
                    "velocity_mps": 58,
                    "rcs_dbsm": -9,
                    "snr_db": 20,
                }
            ]
        },
    )
    manager.ingest_scan(
        configs[0].radar_id,
        {
            "plots": [
                {
                    "range_m": 12000,
                    "azimuth_deg": 14,
                    "elevation_deg": 4,
                    "velocity_mps": 60,
                    "rcs_dbsm": -8,
                    "snr_db": 18,
                }
            ]
        },
    )

    tracks = manager.process_fused_tracks()
    assert len(tracks) == 1
    track = tracks[0]
    assert track.state is TrackState.CONFIRMED
    assert track.classification == "shahed_class_uav"
    assert set(track.sensor_sources) == {cfg.radar_id for cfg in configs}

    status = manager.get_all_status()
    for cfg in configs:
        assert status[cfg.radar_id]["scans"] == 1
        assert status[cfg.radar_id]["plots"] == 1
        assert status[cfg.radar_id]["correlated"] == 1


def test_ingest_scan_validates_payload_and_rejects_out_of_range_plots() -> None:
    """Input validation should enforce safe radar payload handling."""
    manager = RadarManager()
    config = create_krechet_radar_suite(manager)[0]

    with pytest.raises(ValueError, match="Unknown radar_id"):
        manager.ingest_scan("missing-radar", {"plots": []})

    with pytest.raises(ValueError, match="must include a list"):
        manager.ingest_scan(config.radar_id, {"plots": "bad"})

    accepted = manager.ingest_scan(
        config.radar_id,
        {
            "plots": [
                {
                    "range_m": config.max_range_m + 1.0,
                    "azimuth_deg": 0.0,
                    "elevation_deg": 0.0,
                    "velocity_mps": 0.0,
                    "rcs_dbsm": -20.0,
                    "snr_db": 5.0,
                }
            ]
        },
    )
    assert accepted == []
    status = manager.get_all_status()[config.radar_id]
    assert status["scans"] == 1
    assert status["plots"] == 0
