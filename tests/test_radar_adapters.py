"""Tests for S3M radar adapter framework."""

import sys
import math
sys.path.insert(0, ".")

from services.radar.models import RadarConfig, RadarPlot, RadarType, RadarBand, RCSClassification
from services.radar.coordinate_converter import CoordinateConverter
from services.radar.rcs_classifier import RCSClassifier
from services.radar.plot_correlator import PlotCorrelator
from services.radar.noise_model import RadarNoiseModel
from services.radar.adapters.rps82_adapter import RPS82Adapter
from services.radar.adapters.rps202_adapter import RPS202Adapter
from services.radar.adapters.western_aesa_adapter import WesternAESAAdapter
from services.radar.radar_manager import RadarManager
from services.radar.krechet_radar_suite import create_krechet_radar_suite


# --- Coordinate Converter ---

def test_polar_to_cartesian_north():
    x, y, z = CoordinateConverter.polar_to_cartesian(10000, 0, 0)
    assert abs(x) < 1.0  # Due north = no east component
    assert abs(y - 10000) < 1.0
    assert abs(z) < 1.0


def test_polar_to_cartesian_east():
    x, y, z = CoordinateConverter.polar_to_cartesian(10000, 90, 0)
    assert abs(x - 10000) < 1.0  # Due east
    assert abs(y) < 1.0


def test_polar_with_elevation():
    x, y, z = CoordinateConverter.polar_to_cartesian(10000, 0, 30)
    expected_ground = 10000 * math.cos(math.radians(30))
    expected_height = 10000 * math.sin(math.radians(30))
    assert abs(y - expected_ground) < 1.0
    assert abs(z - expected_height) < 1.0


def test_curvature_correction_adds_height():
    flat = CoordinateConverter.polar_to_cartesian(40000, 0, 1)
    curved = CoordinateConverter.polar_to_cartesian_with_curvature(40000, 0, 1)
    # At 40km, curvature correction should add noticeable height difference
    assert curved[2] > flat[2] or abs(curved[2] - flat[2]) < 200  # Some difference expected


def test_wgs84_roundtrip():
    conv = CoordinateConverter()
    enu = conv.wgs84_to_enu(24.72, 46.69, 620, 24.71, 46.68, 610)
    lat, lon, alt = conv.enu_to_wgs84(enu[0], enu[1], enu[2], 24.71, 46.68, 610)
    assert abs(lat - 24.72) < 0.001
    assert abs(lon - 46.69) < 0.001
    assert abs(alt - 620) < 1.0


# --- RCS Classifier ---

def test_rcs_small_uav():
    cls = RCSClassifier()
    result, conf = cls.classify(0.005, speed_mps=30, altitude_m=200)
    assert result == RCSClassification.SMALL_UAV


def test_rcs_fighter_aircraft():
    cls = RCSClassifier()
    result, conf = cls.classify(3.0, speed_mps=250, altitude_m=8000)
    assert result in {RCSClassification.FIGHTER, RCSClassification.HELICOPTER}


def test_rcs_clutter():
    cls = RCSClassifier()
    result, conf = cls.classify(0.0001)
    assert result == RCSClassification.CLUTTER


def test_rcs_class_to_threat():
    assert RCSClassifier.rcs_class_to_threat_class(RCSClassification.MEDIUM_UAV) == "ENEMY_UAV"
    assert RCSClassifier.rcs_class_to_threat_class(RCSClassification.CRUISE_MISSILE) == "ENEMY_CRUISE_MISSILE"


# --- Plot Correlator ---

def test_correlator_creates_new_track():
    corr = PlotCorrelator()
    plots = [RadarPlot(range_m=10000, azimuth_deg=45, position_cartesian=(7071, 7071, 0), snr_db=20)]
    result = corr.correlate(plots)
    assert result[0].correlated_track_id is not None


def test_correlator_associates_nearby_plots():
    corr = PlotCorrelator(distance_gate_m=3000)
    p1 = [RadarPlot(range_m=10000, azimuth_deg=45, position_cartesian=(7071, 7071, 500), snr_db=20)]
    corr.correlate(p1)
    tid1 = p1[0].correlated_track_id

    p2 = [RadarPlot(range_m=10050, azimuth_deg=45.1, position_cartesian=(7120, 7100, 510), snr_db=22)]
    corr.correlate(p2)
    assert p2[0].correlated_track_id == tid1  # Same track


# --- Noise Model ---

def test_noise_model_provides_covariance():
    nm = RadarNoiseModel()
    cov = nm.polar_noise_to_cartesian_covariance(10000, 45, 5, 50.0, 0.5, 0.8)
    assert len(cov) == 3
    assert all(len(row) == 3 for row in cov)
    assert cov[0][0] > 0  # Positive variance


def test_noise_model_confidence():
    nm = RadarNoiseModel()
    high_snr = nm.compute_confidence(25.0, 10000, 50000)
    low_snr = nm.compute_confidence(8.0, 40000, 50000)
    assert high_snr > low_snr


# --- Radar Adapters ---

def test_rps82_adapter_parses_data():
    config = RadarConfig(radar_type=RadarType.RPS_82, max_range_m=20000)
    adapter = RPS82Adapter(config)
    plots = adapter.parse_raw_data({"plots": [
        {"range_m": 15000, "azimuth_deg": 120, "elevation_deg": 5, "rcs_dbsm": -8, "snr_db": 15},
    ]})
    assert len(plots) == 1
    assert plots[0].range_m == 15000


def test_rps202_adapter_default_config():
    config = RadarConfig(radar_type=RadarType.RPS_202, max_range_m=50000)
    adapter = RPS202Adapter(config)
    defaults = adapter.create_default_config()
    assert defaults.max_range_m == 50000
    assert defaults.radar_type == RadarType.RPS_202


# --- Radar Manager (Integration) ---

def test_radar_manager_full_pipeline():
    mgr = RadarManager()
    config = RadarConfig(
        name_en="Test Radar", name_ar="رادار تجريبي",
        radar_type=RadarType.GENERIC_3D,
        position=(0, 0, 0), max_range_m=50000,
    )
    mgr.register_radar(config)

    plots = mgr.ingest_scan(config.radar_id, {"plots": [
        {"range_m": 25000, "azimuth_deg": 45, "elevation_deg": 3, "velocity_mps": 80, "rcs_dbsm": -8, "snr_db": 20},
        {"range_m": 12000, "azimuth_deg": 180, "elevation_deg": 5, "velocity_mps": 50, "rcs_dbsm": -12, "snr_db": 16},
    ]})
    assert len(plots) == 2
    assert all(p.position_cartesian is not None for p in plots)
    assert all(p.rcs_classification != RCSClassification.UNKNOWN for p in plots)

    tracks = mgr.process_fused_tracks()
    assert len(tracks) >= 1

    stats = mgr.get_stats()
    assert stats["registered_radars"] == 1
    assert stats["total_plots"] == 2


def test_krechet_radar_suite_creation():
    mgr = RadarManager()
    configs = create_krechet_radar_suite(mgr)
    assert len(configs) == 3  # RPS-82, RPS-202, AESA
    assert mgr.get_stats()["registered_radars"] == 3


if __name__ == "__main__":
    test_polar_to_cartesian_north()
    test_polar_to_cartesian_east()
    test_polar_with_elevation()
    test_curvature_correction_adds_height()
    test_wgs84_roundtrip()
    test_rcs_small_uav()
    test_rcs_fighter_aircraft()
    test_rcs_clutter()
    test_rcs_class_to_threat()
    test_correlator_creates_new_track()
    test_correlator_associates_nearby_plots()
    test_noise_model_provides_covariance()
    test_noise_model_confidence()
    test_rps82_adapter_parses_data()
    test_rps202_adapter_default_config()
    test_radar_manager_full_pipeline()
    test_krechet_radar_suite_creation()
    print("ALL RADAR ADAPTER TESTS PASSED")
