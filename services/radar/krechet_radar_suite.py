"""Pre-built Krechet-like radar suite templates.

Military context:
This module provides deterministic multi-radar compositions to emulate command
post deployments that integrate 10+ heterogeneous radar channels in one COP.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians
from typing import List, Sequence, Tuple

from services.radar.models import RadarBand, RadarConfig, RadarType
from services.radar.radar_manager import RadarManager


def _offset_lla(origin: Tuple[float, float, float], east_m: float, north_m: float, up_m: float = 0.0) -> Tuple[float, float, float]:
    lat_deg, lon_deg, alt_m = origin
    delta_lat = north_m / 111_320.0
    lon_scale = max(0.1, cos(radians(lat_deg)))
    delta_lon = east_m / (111_320.0 * lon_scale)
    return (lat_deg + delta_lat, lon_deg + delta_lon, alt_m + up_m)


@dataclass(frozen=True)
class KrechetRadarSuite:
    """Container for a prebuilt tactical radar order of battle."""

    suite_name: str
    radar_configs: Sequence[RadarConfig]


def build_krechet_demo_suite(
    origin_lla: Tuple[float, float, float] = (24.7136, 46.6753, 620.0),
) -> KrechetRadarSuite:
    """Build a 10-radar mixed suite including RPS-82/RPS-202 and equivalents."""
    configs: List[RadarConfig] = [
        RadarConfig(
            radar_id="rps82-alpha",
            radar_type=RadarType.RPS_82,
            radar_band=RadarBand.X_BAND,
            name_en="RPS-82 Alpha",
            name_ar="آر بي إس-82 ألفا",
            position_lla=_offset_lla(origin_lla, -2_500.0, 800.0),
            scan_rate_hz=1.2,
            beam_width_az_deg=2.4,
            beam_width_el_deg=6.0,
            max_range_m=32_000.0,
            doppler_resolution_mps=0.8,
        ),
        RadarConfig(
            radar_id="rps202-bravo",
            radar_type=RadarType.RPS_202,
            radar_band=RadarBand.S_BAND,
            name_en="RPS-202 Bravo",
            name_ar="آر بي إس-202 برافو",
            position_lla=_offset_lla(origin_lla, 3_200.0, -1_000.0),
            scan_rate_hz=1.0,
            beam_width_az_deg=1.4,
            beam_width_el_deg=2.8,
            max_range_m=75_000.0,
            doppler_resolution_mps=0.45,
        ),
        RadarConfig(
            radar_id="western-aesa-charlie",
            radar_type=RadarType.WESTERN_AESA,
            radar_band=RadarBand.S_BAND,
            name_en="Western AESA Charlie",
            name_ar="رادار مصفوفة غربي تشارلي",
            position_lla=_offset_lla(origin_lla, 5_500.0, 3_000.0),
            scan_rate_hz=1.6,
            beam_width_az_deg=1.0,
            beam_width_el_deg=2.0,
            max_range_m=120_000.0,
            doppler_resolution_mps=0.3,
        ),
    ]

    # Military/tactical note:
    # Add additional channels to mirror a Krechet-style multi-radar node with
    # overlapping sectors and redundancy against jamming or local outages.
    for index in range(7):
        configs.append(
            RadarConfig(
                radar_id=f"generic3d-{index+1}",
                radar_type=RadarType.GENERIC_3D,
                radar_band=RadarBand.C_BAND if index % 2 == 0 else RadarBand.X_BAND,
                name_en=f"Generic 3D Radar {index+1}",
                name_ar=f"رادار ثلاثي الأبعاد {index+1}",
                position_lla=_offset_lla(
                    origin_lla,
                    east_m=-6_000.0 + index * 1_600.0,
                    north_m=-4_500.0 + index * 900.0,
                ),
                scan_rate_hz=0.8 + (index * 0.07),
                beam_width_az_deg=1.5 + (index * 0.1),
                beam_width_el_deg=3.0 + (index * 0.15),
                max_range_m=45_000.0 + index * 4_000.0,
                doppler_resolution_mps=0.5 + index * 0.05,
            )
        )
    return KrechetRadarSuite(suite_name="krechet-demo-suite", radar_configs=configs)


def load_krechet_suite(
    manager: RadarManager,
    origin_lla: Tuple[float, float, float] = (24.7136, 46.6753, 620.0),
) -> KrechetRadarSuite:
    """Register a full Krechet-like suite into a RadarManager."""
    suite = build_krechet_demo_suite(origin_lla=origin_lla)
    for config in suite.radar_configs:
        manager.register_radar(config)
    return suite
