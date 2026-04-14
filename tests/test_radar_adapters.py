"""Unit tests for the S3M Radar Adapter Framework."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter
from services.radar.coordinate_converter import CoordinateConverter
from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarScan, RadarType, ScanMode
from services.radar.plot_correlator import PlotCorrelator
from services.radar.radar_manager import RadarManager
from services.radar.rcs_classifier import RCSClassifier


def _sample_config(radar_id: str = "radar-1", radar_type: RadarType = RadarType.GENERIC_3D) -> RadarConfig:
    return RadarConfig(
        radar_id=radar_id,
        radar_type=radar_type,
        radar_band=RadarBand.X_BAND,
        name_en="Test Radar",
        name_ar="رادار اختبار",
        position_lla=(24.7136, 46.6753, 620.0),
        orientation_deg=(0.0, 0.0, 0.0),
        scan_rate_hz=1.0,
        beam_width_az_deg=1.8,
        beam_width_el_deg=3.2,
        min_range_m=100.0,
        max_range_m=100_000.0,
        doppler_resolution_mps=0.6,
    )


def test_coordinate_converter_polar_to_enu_nominal_axes():
    converter = CoordinateConverter(24.7136, 46.6753, 620.0)
    east, north, up = converter.polar_to_enu(
        range_m=1000.0,
        azimuth_deg=90.0,
        elevation_deg=0.0,
        radar_position_lla=(24.7136, 46.6753, 620.0),
        orientation_deg=(0.0, 0.0, 0.0),
        apply_earth_curvature=False,
    )
    assert abs(east - 1000.0) < 1e-3
    assert abs(north) < 1e-3
    assert abs(up) < 1e-3


def test_rcs_classifier_profiles():
    classifier = RCSClassifier()
    assert classifier.classify(0.005, 20.0).value == "SMALL_UAV"
    assert classifier.classify(0.3, 240.0).value == "CRUISE_MISSILE"
    assert classifier.classify(20.0, 120.0).value == "LARGE_AIRCRAFT"
    assert classifier.to_target_allocator_label(classifier.classify(0.3, 240.0)) == "ENEMY_CRUISE_MISSILE"


def test_plot_correlator_links_close_plots():
    now = datetime.now(timezone.utc)
    scan1 = RadarScan(
        radar_id="r-1",
        scan_mode=ScanMode.SEARCH,
        timestamp=now,
        scan_id="scan-1",
        scan_index=1,
        plots=[
            RadarPlot(
                plot_id="p1",
                timestamp=now,
                range_m=10_000.0,
                azimuth_deg=30.0,
                elevation_deg=1.5,
                radial_velocity_mps=120.0,
                rcs_m2=0.2,
                snr_db=12.0,
            )
        ],
    )
    scan2 = RadarScan(
        radar_id="r-1",
        scan_mode=ScanMode.SEARCH,
        timestamp=now + timedelta(seconds=1),
        scan_id="scan-2",
        scan_index=2,
        plots=[
            RadarPlot(
                plot_id="p2",
                timestamp=now + timedelta(seconds=1),
                range_m=10_120.0,
                azimuth_deg=30.4,
                elevation_deg=1.6,
                radial_velocity_mps=124.0,
                rcs_m2=0.22,
                snr_db=12.0,
            )
        ],
    )
    correlator = PlotCorrelator()
    assert correlator.correlate(scan1) == []
    correlations = correlator.correlate(scan2)
    assert len(correlations) == 1
    assert correlations[0].previous_plot_id == "p1"
    assert correlations[0].current_plot_id == "p2"
    assert correlations[0].score > 0.0


def test_generic_3d_adapter_emits_sensor_readings():
    config = _sample_config("adapter-radar", RadarType.GENERIC_3D)
    adapter = Generic3DRadarAdapter(config)
    converter = CoordinateConverter(*config.position_lla)
    scan = adapter.parse_raw_scan(
        {
            "scan_id": "s-1",
            "scan_index": 1,
            "scan_mode": "VOLUME",
            "plots": [
                {
                    "plot_id": "plot-1",
                    "range_m": 8000.0,
                    "azimuth_deg": 45.0,
                    "elevation_deg": 2.0,
                    "radial_velocity_mps": 75.0,
                    "rcs_m2": 0.03,
                    "snr_db": 16.0,
                }
            ],
        }
    )
    readings = adapter.adapt_scan(scan=scan, converter=converter, correlations=[])
    assert len(readings) == 1
    reading = readings[0]
    assert reading.sensor_id == "adapter-radar"
    assert reading.position is not None
    assert reading.data["classification"] == "MEDIUM_UAV"
    assert "noise_covariance" in reading.data


def test_radar_manager_register_ingest_process_pipeline():
    manager = RadarManager(reference_origin_lla=(24.7136, 46.6753, 620.0))
    manager.register_radar(_sample_config("rm-1", RadarType.RPS_202))
    raw_scan = {
        "scan_id": "rm-scan-1",
        "scan_index": 1,
        "tracks": [
            {
                "track_id": "rm-target-1",
                "range_m": 12000.0,
                "bearing_deg": 60.0,
                "el_deg": 3.0,
                "doppler_mps": 210.0,
                "rcs_m2": 0.25,
                "snr_db": 17.0,
            }
        ],
    }
    readings, correlations = manager.ingest_scan_with_correlations("rm-1", raw_scan)
    assert len(readings) == 1
    assert readings[0].data["target_allocator_classification"] == "ENEMY_CRUISE_MISSILE"
    assert correlations == []
    tracks = manager.process_fusion()
    assert len(tracks) >= 1
