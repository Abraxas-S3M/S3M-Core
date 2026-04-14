"""Unit tests for radar measurement noise modeling.

Military context:
These checks verify that EKF observation weighting honors radar-specific error
profiles, which is critical for track quality under contested sensor conditions.
"""

from __future__ import annotations

import math

import pytest

from services.radar.models import RadarConfig, RadarType
from services.radar.noise_model import RadarNoiseModel


def test_radar_config_validates_required_and_non_negative_fields() -> None:
    with pytest.raises(ValueError):
        RadarConfig(radar_id="")
    with pytest.raises(ValueError):
        RadarConfig(radar_id="radar-1", max_range_m=-1.0)
    with pytest.raises(ValueError):
        RadarConfig(radar_id="radar-1", range_noise_std_m=-0.1)


def test_radar_config_coerces_radar_type_string_enum() -> None:
    cfg = RadarConfig(radar_id="radar-1", radar_type="aesa_panel")
    assert cfg.radar_type is RadarType.AESA_PANEL


def test_get_polar_noise_uses_defaults_and_overrides() -> None:
    model = RadarNoiseModel()
    cfg_default = RadarConfig(radar_id="r-default", radar_type=RadarType.RPS_202)
    assert model.get_polar_noise(cfg_default) == (50.0, 0.7, 1.5, 5.0)

    cfg_override = RadarConfig(
        radar_id="r-override",
        radar_type=RadarType.RPS_202,
        range_noise_std_m=33.0,
        azimuth_noise_std_deg=0.4,
        elevation_noise_std_deg=1.1,
        velocity_noise_std_mps=2.5,
    )
    assert model.get_polar_noise(cfg_override) == (33.0, 0.4, 1.1, 2.5)


def test_get_polar_noise_forces_zero_elevation_for_generic_2d() -> None:
    model = RadarNoiseModel()
    cfg = RadarConfig(
        radar_id="r-2d",
        radar_type=RadarType.GENERIC_2D,
        elevation_noise_std_deg=1.0,
    )
    assert model.get_polar_noise(cfg)[2] == 0.0


def test_polar_noise_to_cartesian_covariance_matches_expected_axis_case() -> None:
    model = RadarNoiseModel()
    cov = model.polar_noise_to_cartesian_covariance(
        range_m=1000.0,
        azimuth_deg=0.0,
        elevation_deg=0.0,
        range_noise_m=10.0,
        az_noise_deg=1.0,
        el_noise_deg=2.0,
    )

    expected_xx = 1000.0**2 * math.radians(1.0) ** 2
    expected_yy = 10.0**2
    expected_zz = 1000.0**2 * math.radians(2.0) ** 2
    assert cov[0][0] == pytest.approx(expected_xx)
    assert cov[1][1] == pytest.approx(expected_yy)
    assert cov[2][2] == pytest.approx(expected_zz)
    assert cov[0][1] == pytest.approx(cov[1][0])
    assert cov[0][2] == pytest.approx(cov[2][0])
    assert cov[1][2] == pytest.approx(cov[2][1])
    assert cov[0][1] == pytest.approx(0.0, abs=1e-9)
    assert cov[0][2] == pytest.approx(0.0, abs=1e-9)
    assert cov[1][2] == pytest.approx(0.0, abs=1e-9)


def test_noise_model_rejects_invalid_inputs() -> None:
    model = RadarNoiseModel()

    with pytest.raises(TypeError):
        model.get_polar_noise(config=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        model.polar_noise_to_cartesian_covariance(
            range_m=-1.0,
            azimuth_deg=0.0,
            elevation_deg=0.0,
            range_noise_m=1.0,
            az_noise_deg=1.0,
            el_noise_deg=1.0,
        )
    with pytest.raises(ValueError):
        model.compute_confidence(snr_db=10.0, range_m=1000.0, max_range_m=-1.0)


def test_compute_confidence_increases_with_better_geometry_and_snr() -> None:
    model = RadarNoiseModel()
    degraded = model.compute_confidence(snr_db=5.0, range_m=40_000.0, max_range_m=40_000.0)
    high_quality = model.compute_confidence(snr_db=35.0, range_m=5_000.0, max_range_m=40_000.0)

    assert 0.0 < degraded <= 0.98
    assert 0.0 < high_quality <= 0.98
    assert high_quality > degraded
