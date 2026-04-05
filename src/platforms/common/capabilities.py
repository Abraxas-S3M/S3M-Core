"""Pre-configured platform capability profiles for S3M-Core adapters.

UNCLASSIFIED - CLOSED-RANGE TRAINING USE ONLY
"""

from __future__ import annotations

import copy
from typing import Dict

from .contracts import PlatformCapabilities
from .messages import PlatformType


# Mobility + fire support baseline for convoy protection in contested terrain.
HMMWV_M1151_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.UGV,
    platform_model="HMMWV M1151",
    has_mobility=True,
    has_weapon_payload=True,
    has_isr_payload=True,
    max_speed_mps=31.0,
    sensor_types=["eo", "ir", "gps", "imu", "rangefinder"],
    comms_types=["mesh_radio", "satcom", "lte"],
    autonomy_levels_supported=[0, 1, 2],
    operating_temp_range_c=(-32.0, 52.0),
    environmental_rating="all_terrain",
)

# Tactical ISR + overwatch for perimeter and route reconnaissance.
WARWAR_UAS_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.UAV,
    platform_model="WarWar UAS",
    has_mobility=True,
    has_weapon_payload=False,
    has_isr_payload=True,
    max_speed_mps=45.0,
    sensor_types=["eo", "ir", "laser_rangefinder", "ais", "adsb", "gps", "imu"],
    comms_types=["mesh_radio", "satcom", "line_of_sight_rf"],
    autonomy_levels_supported=[0, 1, 2, 3],
    operating_temp_range_c=(-20.0, 50.0),
    environmental_rating="wind_hardened",
)

# Littoral patrol and maritime convoy security in denied coastal waters.
G24_USV_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.USV,
    platform_model="G24 USV",
    has_mobility=True,
    has_weapon_payload=True,
    has_isr_payload=True,
    max_speed_mps=22.0,
    sensor_types=["eo", "ir", "surface_radar", "gps", "imu", "sonar"],
    comms_types=["mesh_radio", "satcom", "maritime_vhf"],
    autonomy_levels_supported=[0, 1, 2],
    operating_temp_range_c=(-15.0, 55.0),
    environmental_rating="salt_fog_resistant",
)

# Fixed-area persistent surveillance and early warning node.
HORIZON_TOWER_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.FIXED_NODE,
    platform_model="Horizon Tower",
    has_mobility=False,
    has_weapon_payload=False,
    has_isr_payload=True,
    max_speed_mps=0.0,
    sensor_types=["eo", "ir", "ground_radar", "acoustic_array"],
    comms_types=["fiber", "mesh_radio", "satcom"],
    autonomy_levels_supported=[0, 1],
    operating_temp_range_c=(-35.0, 60.0),
    environmental_rating="static_hardened",
)

# RWS profile for point defense and protected force mobility.
RCWS_12_7_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.PAYLOAD,
    platform_model="RCWS 12.7",
    has_mobility=False,
    has_weapon_payload=True,
    has_isr_payload=False,
    max_speed_mps=0.0,
    sensor_types=["stabilized_eo", "stabilized_ir", "laser_rangefinder"],
    comms_types=["vehicle_bus", "ethernet"],
    autonomy_levels_supported=[0, 1, 2],
    operating_temp_range_c=(-25.0, 55.0),
    environmental_rating="recoil_hardened",
)

RCWS_14_5_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.PAYLOAD,
    platform_model="RCWS 14.5",
    has_mobility=False,
    has_weapon_payload=True,
    has_isr_payload=False,
    max_speed_mps=0.0,
    sensor_types=["stabilized_eo", "stabilized_ir", "laser_rangefinder"],
    comms_types=["vehicle_bus", "ethernet"],
    autonomy_levels_supported=[0, 1, 2],
    operating_temp_range_c=(-25.0, 55.0),
    environmental_rating="recoil_hardened",
)

SICH_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.PAYLOAD,
    platform_model="SICH 30mm",
    has_mobility=False,
    has_weapon_payload=True,
    has_isr_payload=False,
    max_speed_mps=0.0,
    sensor_types=["stabilized_eo", "stabilized_ir", "radar_cueing"],
    comms_types=["vehicle_bus", "ethernet"],
    autonomy_levels_supported=[0, 1, 2],
    operating_temp_range_c=(-25.0, 55.0),
    environmental_rating="heavy_recoil_hardened",
)

ORION_ZU23_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.PAYLOAD,
    platform_model="ORION ZU-23",
    has_mobility=False,
    has_weapon_payload=True,
    has_isr_payload=False,
    max_speed_mps=0.0,
    sensor_types=["stabilized_eo", "stabilized_ir", "radar_cueing"],
    comms_types=["vehicle_bus", "ethernet"],
    autonomy_levels_supported=[0, 1, 2],
    operating_temp_range_c=(-20.0, 50.0),
    environmental_rating="heavy_recoil_hardened",
)

MANPADS_CAPABILITIES = PlatformCapabilities(
    platform_type=PlatformType.PAYLOAD,
    platform_model="MANPADS",
    has_mobility=False,
    has_weapon_payload=True,
    has_isr_payload=False,
    max_speed_mps=0.0,
    sensor_types=["ir_seeker", "target_cueing"],
    comms_types=["vehicle_bus", "manpack_radio"],
    autonomy_levels_supported=[0, 1],
    operating_temp_range_c=(-30.0, 50.0),
    environmental_rating="portable_field",
)


CAPABILITY_REGISTRY: Dict[str, PlatformCapabilities] = {
    "hmmwv_m1151": HMMWV_M1151_CAPABILITIES,
    "warwar_uas": WARWAR_UAS_CAPABILITIES,
    "g24_usv": G24_USV_CAPABILITIES,
    "horizon_tower": HORIZON_TOWER_CAPABILITIES,
    "rcws_12_7": RCWS_12_7_CAPABILITIES,
    "rcws_14_5": RCWS_14_5_CAPABILITIES,
    "sich_30mm": SICH_CAPABILITIES,
    "orion_zu23": ORION_ZU23_CAPABILITIES,
    "manpads": MANPADS_CAPABILITIES,
}


def get_capabilities(platform_key: str) -> PlatformCapabilities:
    """Return a defensive copy of capability profile by registry key."""
    if not isinstance(platform_key, str) or not platform_key.strip():
        raise ValueError("platform_key must be a non-empty string")
    key = platform_key.strip().lower()
    if key not in CAPABILITY_REGISTRY:
        available = ", ".join(sorted(CAPABILITY_REGISTRY))
        raise KeyError(f"unknown platform capability key '{platform_key}'. Available: {available}")
    return copy.deepcopy(CAPABILITY_REGISTRY[key])


__all__ = [
    "HMMWV_M1151_CAPABILITIES",
    "WARWAR_UAS_CAPABILITIES",
    "G24_USV_CAPABILITIES",
    "HORIZON_TOWER_CAPABILITIES",
    "RCWS_12_7_CAPABILITIES",
    "RCWS_14_5_CAPABILITIES",
    "SICH_CAPABILITIES",
    "ORION_ZU23_CAPABILITIES",
    "MANPADS_CAPABILITIES",
    "CAPABILITY_REGISTRY",
    "get_capabilities",
]
