"""Pre-built radar suite templates matching Krechet 9C905 configurations.

Military context:
The Krechet demo at the LIPA training ground used RPS-82 + RPS-202 as the
radar reconnaissance equipment feeding the C3 VAN. This module creates
equivalent radar configurations for S3M.
"""

from __future__ import annotations

from math import isfinite
from typing import List, Tuple

from services.radar.models import RadarBand, RadarConfig, RadarType, ScanMode
from services.radar.radar_manager import RadarManager


def _validate_center(center: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if len(center) != 3:
        raise ValueError("center must contain exactly three coordinates")
    x, y, z = (float(center[0]), float(center[1]), float(center[2]))
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError("center coordinates must be finite numbers")
    return (x, y, z)


def create_krechet_radar_suite(
    manager: RadarManager,
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> List[RadarConfig]:
    """Create the Krechet demo radar suite: RPS-82 + RPS-202 + AESA.

    Matches the LIPA training ground demo structure (slide 10 of the presentation).
    """
    if not isinstance(manager, RadarManager):
        raise TypeError("manager must be a RadarManager instance")
    center = _validate_center(center)
    configs: List[RadarConfig] = []

    # RPS-82 secures forward low-altitude warning in the tactical screen.
    rps82 = RadarConfig(
        name_en="RPS-82 Forward Radar",
        name_ar="رادار RPS-82 أمامي",
        radar_type=RadarType.RPS_82,
        band=RadarBand.X_BAND,
        scan_mode=ScanMode.ROTATING,
        position=(center[0] + 1000.0, center[1] + 2000.0, center[2]),
        max_range_m=20_000,
        min_range_m=100,
        max_elevation_deg=60.0,
        has_elevation=True,
        has_doppler=True,
        beam_width_az_deg=2.5,
        scan_rate_rpm=12.0,
        min_detectable_rcs_dbsm=-15.0,
        range_noise_std_m=75.0,
        azimuth_noise_std_deg=1.0,
        elevation_noise_std_deg=2.0,
    )
    configs.append(manager.register_radar(rps82))

    # RPS-202 sits on the C3 vehicle to maintain medium-range track continuity.
    rps202 = RadarConfig(
        name_en="RPS-202 C3 VAN Radar",
        name_ar="رادار RPS-202 عربة القيادة",
        radar_type=RadarType.RPS_202,
        band=RadarBand.S_BAND,
        scan_mode=ScanMode.ROTATING,
        position=(center[0], center[1], center[2] + 5.0),
        max_range_m=50_000,
        min_range_m=200,
        max_elevation_deg=70.0,
        has_elevation=True,
        has_doppler=True,
        beam_width_az_deg=1.8,
        scan_rate_rpm=6.0,
        min_detectable_rcs_dbsm=-10.0,
        range_noise_std_m=50.0,
        azimuth_noise_std_deg=0.7,
        elevation_noise_std_deg=1.5,
    )
    configs.append(manager.register_radar(rps202))

    # AESA augments small-target discrimination for layered defense rehearsals.
    aesa = RadarConfig(
        name_en="AESA Search Radar",
        name_ar="رادار بحث إلكتروني متقدم",
        radar_type=RadarType.AESA_WESTERN,
        band=RadarBand.C_BAND,
        scan_mode=ScanMode.ELECTRONIC,
        position=(center[0] - 500.0, center[1] + 500.0, center[2] + 8.0),
        max_range_m=75_000,
        min_range_m=100,
        max_elevation_deg=80.0,
        has_elevation=True,
        has_doppler=True,
        beam_width_az_deg=0.8,
        update_rate_hz=2.0,
        min_detectable_rcs_dbsm=-20.0,
        range_noise_std_m=15.0,
        azimuth_noise_std_deg=0.3,
        elevation_noise_std_deg=0.4,
    )
    configs.append(manager.register_radar(aesa))

    return configs
