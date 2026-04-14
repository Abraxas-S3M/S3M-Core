"""Radar measurement noise models for EKF tuning.

Military context:
Different radar types have different measurement accuracies. A rotating
S-band surveillance radar has different noise characteristics than an
X-band AESA tracker. The noise model provides per-radar-type measurement
covariance that the EKF uses to weight observations correctly during fusion.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from services.radar.models import RadarConfig, RadarType


def _validate_finite(value: float, *, field_name: str) -> float:
    validated = float(value)
    if not math.isfinite(validated):
        raise ValueError(f"{field_name} must be a finite number")
    return validated


def _validate_non_negative(value: float, *, field_name: str) -> float:
    validated = _validate_finite(value, field_name=field_name)
    if validated < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return validated


# Default noise parameters by radar type
# (range_noise_m, azimuth_noise_deg, elevation_noise_deg, velocity_noise_mps)
DEFAULT_NOISE: Dict[RadarType, Tuple[float, float, float, float]] = {
    RadarType.RPS_82: (75.0, 1.0, 2.0, 8.0),
    RadarType.RPS_202: (50.0, 0.7, 1.5, 5.0),
    RadarType.GENERIC_2D: (100.0, 1.2, 0.0, 0.0),  # No elevation, no Doppler
    RadarType.GENERIC_3D: (60.0, 0.8, 1.0, 6.0),
    RadarType.AESA_WESTERN: (15.0, 0.3, 0.4, 2.0),
    RadarType.AESA_PANEL: (20.0, 0.4, 0.5, 3.0),
    RadarType.DOPPLER_CW: (200.0, 2.0, 0.0, 1.0),  # Poor range, good velocity
    RadarType.CUSTOM: (80.0, 1.0, 1.5, 5.0),
}


class RadarNoiseModel:
    """Compute measurement noise covariance for EKF observation weighting."""

    def __init__(self) -> None:
        self.defaults = dict(DEFAULT_NOISE)

    def get_polar_noise(self, config: RadarConfig) -> Tuple[float, float, float, float]:
        """Return (range_noise_m, az_noise_deg, el_noise_deg, vel_noise_mps) for a radar config."""
        if not isinstance(config, RadarConfig):
            raise TypeError("config must be a RadarConfig instance")

        base = self.defaults.get(config.radar_type, self.defaults[RadarType.CUSTOM])
        # Tactical doctrine: explicit per-radar calibration values take precedence over defaults.
        range_noise = config.range_noise_std_m if config.range_noise_std_m > 0.0 else base[0]
        az_noise = config.azimuth_noise_std_deg if config.azimuth_noise_std_deg > 0.0 else base[1]
        if config.radar_type is RadarType.GENERIC_2D:
            el_noise = 0.0
        else:
            el_noise = config.elevation_noise_std_deg if config.elevation_noise_std_deg > 0.0 else base[2]
        vel_noise = config.velocity_noise_std_mps if config.velocity_noise_std_mps > 0.0 else base[3]
        return (range_noise, az_noise, el_noise, vel_noise)

    def polar_noise_to_cartesian_covariance(
        self,
        range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
        range_noise_m: float,
        az_noise_deg: float,
        el_noise_deg: float,
    ) -> List[List[float]]:
        """Convert polar measurement noise to 3x3 Cartesian position covariance.

        Uses first-order error propagation through the polar-to-Cartesian transform.
        This gives the EKF the correct R matrix for weighting this particular observation.
        """
        range_m = _validate_non_negative(range_m, field_name="range_m")
        azimuth_deg = _validate_finite(azimuth_deg, field_name="azimuth_deg")
        elevation_deg = _validate_finite(elevation_deg, field_name="elevation_deg")
        range_noise_m = _validate_non_negative(range_noise_m, field_name="range_noise_m")
        az_noise_deg = _validate_non_negative(az_noise_deg, field_name="az_noise_deg")
        el_noise_deg = _validate_non_negative(el_noise_deg, field_name="el_noise_deg")

        az_rad = math.radians(azimuth_deg)
        el_rad = math.radians(elevation_deg)
        sigma_r = range_noise_m
        sigma_az = math.radians(az_noise_deg)
        sigma_el = math.radians(el_noise_deg)

        cos_az = math.cos(az_rad)
        sin_az = math.sin(az_rad)
        cos_el = math.cos(el_rad)
        sin_el = math.sin(el_rad)

        # Jacobian of polar->Cartesian: d(x,y,z)/d(r,az,el)
        # x = r * cos(el) * sin(az)
        # y = r * cos(el) * cos(az)
        # z = r * sin(el)
        dx_dr = cos_el * sin_az
        dx_daz = range_m * cos_el * cos_az
        dx_del = -range_m * sin_el * sin_az

        dy_dr = cos_el * cos_az
        dy_daz = -range_m * cos_el * sin_az
        dy_del = -range_m * sin_el * cos_az

        dz_dr = sin_el
        dz_daz = 0.0
        dz_del = range_m * cos_el

        # R_cart = J * R_polar * J^T
        # R_polar = diag(sigma_r^2, sigma_az^2, sigma_el^2)
        sr2 = sigma_r**2
        sa2 = sigma_az**2
        se2 = sigma_el**2

        cov_xx = dx_dr**2 * sr2 + dx_daz**2 * sa2 + dx_del**2 * se2
        cov_yy = dy_dr**2 * sr2 + dy_daz**2 * sa2 + dy_del**2 * se2
        cov_zz = dz_dr**2 * sr2 + dz_daz**2 * sa2 + dz_del**2 * se2

        cov_xy = dx_dr * dy_dr * sr2 + dx_daz * dy_daz * sa2 + dx_del * dy_del * se2
        cov_xz = dx_dr * dz_dr * sr2 + dx_daz * dz_daz * sa2 + dx_del * dz_del * se2
        cov_yz = dy_dr * dz_dr * sr2 + dy_daz * dz_daz * sa2 + dy_del * dz_del * se2

        return [
            [cov_xx, cov_xy, cov_xz],
            [cov_xy, cov_yy, cov_yz],
            [cov_xz, cov_yz, cov_zz],
        ]

    def compute_confidence(self, snr_db: float, range_m: float, max_range_m: float) -> float:
        """Compute detection confidence from SNR and range ratio."""
        snr_db = _validate_finite(snr_db, field_name="snr_db")
        range_m = _validate_non_negative(range_m, field_name="range_m")
        max_range_m = _validate_non_negative(max_range_m, field_name="max_range_m")

        # SNR contribution to confidence in track quality.
        snr_conf = min(1.0, max(0.1, (snr_db - 5.0) / 25.0)) if snr_db > 0.0 else 0.3
        # Tactical range penalty: edge-of-coverage detections are less reliable for fire control.
        range_ratio = range_m / max(max_range_m, 1.0)
        range_conf = max(0.3, 1.0 - range_ratio**2)
        return min(0.98, snr_conf * 0.6 + range_conf * 0.4)
