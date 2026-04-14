"""Radar measurement noise models for tactical fusion tuning.

Military context:
Accurate covariance estimates are required for robust EKF behavior when mixing
high-power long-range radars with short-range low-SNR tactical sensors.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt
from typing import Dict, List

from services.radar.models import RadarConfig, RadarType


def _snr_linear(snr_db: float) -> float:
    return 10.0 ** (float(snr_db) / 10.0)


@dataclass(frozen=True)
class RadarNoiseModel:
    """Compute radar measurement standard deviations and covariance matrices."""

    base_range_std_m: float = 25.0
    min_range_std_m: float = 1.5
    min_angular_std_rad: float = 0.0004
    min_velocity_std_mps: float = 0.2

    def range_std_m(self, snr_db: float) -> float:
        linear = max(_snr_linear(snr_db), 1e-6)
        std = self.base_range_std_m / sqrt(linear)
        return max(self.min_range_std_m, std)

    def angular_std_rad(self, beam_width_deg: float) -> float:
        # Approximate 1-sigma from beamwidth/FWHM relation.
        std = (float(beam_width_deg) * pi / 180.0) / 2.355
        return max(self.min_angular_std_rad, std)

    def velocity_std_mps(self, doppler_resolution_mps: float) -> float:
        std = float(doppler_resolution_mps) / 2.355
        return max(self.min_velocity_std_mps, std)

    def measurement_covariance(self, config: RadarConfig, snr_db: float) -> List[List[float]]:
        range_var = self.range_std_m(snr_db) ** 2
        az_var = self.angular_std_rad(config.beam_width_az_deg) ** 2
        el_var = self.angular_std_rad(config.beam_width_el_deg) ** 2
        vel_var = self.velocity_std_mps(config.doppler_resolution_mps) ** 2
        return [
            [range_var, 0.0, 0.0, 0.0],
            [0.0, az_var, 0.0, 0.0],
            [0.0, 0.0, el_var, 0.0],
            [0.0, 0.0, 0.0, vel_var],
        ]

    def covariance_metadata(self, config: RadarConfig, snr_db: float) -> Dict[str, float]:
        return {
            "sigma_range_m": self.range_std_m(snr_db),
            "sigma_az_rad": self.angular_std_rad(config.beam_width_az_deg),
            "sigma_el_rad": self.angular_std_rad(config.beam_width_el_deg),
            "sigma_velocity_mps": self.velocity_std_mps(config.doppler_resolution_mps),
        }

    @staticmethod
    def default_for_radar_type(radar_type: RadarType) -> "RadarNoiseModel":
        mapping = {
            RadarType.GENERIC_2D: RadarNoiseModel(base_range_std_m=35.0, min_velocity_std_mps=0.8),
            RadarType.GENERIC_3D: RadarNoiseModel(base_range_std_m=25.0, min_velocity_std_mps=0.6),
            RadarType.RPS_82: RadarNoiseModel(base_range_std_m=20.0, min_velocity_std_mps=0.5),
            RadarType.RPS_202: RadarNoiseModel(base_range_std_m=14.0, min_velocity_std_mps=0.35),
            RadarType.WESTERN_AESA: RadarNoiseModel(base_range_std_m=10.0, min_velocity_std_mps=0.25),
        }
        return mapping[radar_type]
