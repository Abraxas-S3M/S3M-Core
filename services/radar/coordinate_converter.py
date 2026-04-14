"""Coordinate conversion helpers for tactical radar integration.

Military context:
Ground radars report detections in polar coordinates relative to local antenna
boresight. These utilities convert those detections into a shared ENU Cartesian
frame so layered batteries and fusion nodes can reason over one geometry model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin, sqrt
from typing import Tuple


WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
EARTH_RADIUS_M = 6_371_000.0


def _validate_lla(latitude_deg: float, longitude_deg: float, altitude_m: float) -> Tuple[float, float, float]:
    lat = float(latitude_deg)
    lon = float(longitude_deg)
    alt = float(altitude_m)
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("latitude_deg must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("longitude_deg must be in [-180, 180]")
    return (lat, lon, alt)


def wgs84_to_ecef(latitude_deg: float, longitude_deg: float, altitude_m: float) -> Tuple[float, float, float]:
    """Convert geodetic WGS84 coordinate to ECEF (meters)."""
    lat_deg, lon_deg, alt_m = _validate_lla(latitude_deg, longitude_deg, altitude_m)
    lat = radians(lat_deg)
    lon = radians(lon_deg)
    sin_lat = sin(lat)
    cos_lat = cos(lat)
    sin_lon = sin(lon)
    cos_lon = cos(lon)
    n = WGS84_A / sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * cos_lon
    y = (n + alt_m) * cos_lat * sin_lon
    z = ((1.0 - WGS84_E2) * n + alt_m) * sin_lat
    return (x, y, z)


def ecef_to_enu(
    x_m: float,
    y_m: float,
    z_m: float,
    ref_latitude_deg: float,
    ref_longitude_deg: float,
    ref_altitude_m: float,
) -> Tuple[float, float, float]:
    """Convert ECEF to local ENU with a reference geodetic origin."""
    ref_lat_deg, ref_lon_deg, ref_alt_m = _validate_lla(ref_latitude_deg, ref_longitude_deg, ref_altitude_m)
    ref_x, ref_y, ref_z = wgs84_to_ecef(ref_lat_deg, ref_lon_deg, ref_alt_m)
    dx = float(x_m) - ref_x
    dy = float(y_m) - ref_y
    dz = float(z_m) - ref_z

    lat = radians(ref_lat_deg)
    lon = radians(ref_lon_deg)
    sin_lat = sin(lat)
    cos_lat = cos(lat)
    sin_lon = sin(lon)
    cos_lon = cos(lon)

    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    return (east, north, up)


def wgs84_to_enu(
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
    ref_latitude_deg: float,
    ref_longitude_deg: float,
    ref_altitude_m: float,
) -> Tuple[float, float, float]:
    """Convert geodetic WGS84 coordinate directly to ENU."""
    x, y, z = wgs84_to_ecef(latitude_deg, longitude_deg, altitude_m)
    return ecef_to_enu(
        x,
        y,
        z,
        ref_latitude_deg=ref_latitude_deg,
        ref_longitude_deg=ref_longitude_deg,
        ref_altitude_m=ref_altitude_m,
    )


def _rotate_enu_vector(
    vector_enu: Tuple[float, float, float],
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
) -> Tuple[float, float, float]:
    """Rotate a vector in ENU with intrinsic yaw-pitch-roll (degrees)."""
    x, y, z = (float(vector_enu[0]), float(vector_enu[1]), float(vector_enu[2]))
    yaw = radians(float(yaw_deg))
    pitch = radians(float(pitch_deg))
    roll = radians(float(roll_deg))

    cy = cos(yaw)
    sy = sin(yaw)
    cp = cos(pitch)
    sp = sin(pitch)
    cr = cos(roll)
    sr = sin(roll)

    # Military/tactical note:
    # This keeps a deterministic 3-axis boresight correction for fielded radars
    # mounted on non-level terrain or angled vehicle masts.
    r00 = cy * cp
    r01 = cy * sp * sr - sy * cr
    r02 = cy * sp * cr + sy * sr
    r10 = sy * cp
    r11 = sy * sp * sr + cy * cr
    r12 = sy * sp * cr - cy * sr
    r20 = -sp
    r21 = cp * sr
    r22 = cp * cr

    out_x = r00 * x + r01 * y + r02 * z
    out_y = r10 * x + r11 * y + r12 * z
    out_z = r20 * x + r21 * y + r22 * z
    return (out_x, out_y, out_z)


def polar_to_cartesian_local(range_m: float, azimuth_deg: float, elevation_deg: float) -> Tuple[float, float, float]:
    """Convert polar radar measurement to local ENU delta (meters)."""
    r = float(range_m)
    if r < 0.0:
        raise ValueError("range_m must be non-negative")
    az = radians(float(azimuth_deg))
    el = radians(float(elevation_deg))
    horizontal = r * cos(el)
    east = horizontal * sin(az)
    north = horizontal * cos(az)
    up = r * sin(el)
    return (east, north, up)


def polar_to_enu(
    range_m: float,
    azimuth_deg: float,
    elevation_deg: float,
    radar_latitude_deg: float,
    radar_longitude_deg: float,
    radar_altitude_m: float,
    reference_latitude_deg: float,
    reference_longitude_deg: float,
    reference_altitude_m: float,
    orientation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    apply_earth_curvature: bool = True,
) -> Tuple[float, float, float]:
    """Convert polar detection to shared ENU Cartesian coordinates."""
    radar_enu = wgs84_to_enu(
        radar_latitude_deg,
        radar_longitude_deg,
        radar_altitude_m,
        reference_latitude_deg,
        reference_longitude_deg,
        reference_altitude_m,
    )
    local_delta = polar_to_cartesian_local(range_m, azimuth_deg, elevation_deg)
    rotated_delta = _rotate_enu_vector(
        local_delta,
        yaw_deg=orientation_deg[0],
        pitch_deg=orientation_deg[1],
        roll_deg=orientation_deg[2],
    )
    east = radar_enu[0] + rotated_delta[0]
    north = radar_enu[1] + rotated_delta[1]
    up = radar_enu[2] + rotated_delta[2]

    if apply_earth_curvature:
        # Tactical approximation:
        # subtract Earth curvature drop so long-range low-altitude tracks do not
        # appear artificially elevated in local tangent-plane geometry.
        ground_distance = sqrt(rotated_delta[0] ** 2 + rotated_delta[1] ** 2)
        curvature_drop = (ground_distance * ground_distance) / (2.0 * EARTH_RADIUS_M)
        up -= curvature_drop
    return (east, north, up)


@dataclass(frozen=True)
class CoordinateConverter:
    """High-level converter wrapper bound to one local ENU reference origin."""

    reference_latitude_deg: float
    reference_longitude_deg: float
    reference_altitude_m: float

    def wgs84_to_enu(self, latitude_deg: float, longitude_deg: float, altitude_m: float) -> Tuple[float, float, float]:
        return wgs84_to_enu(
            latitude_deg,
            longitude_deg,
            altitude_m,
            self.reference_latitude_deg,
            self.reference_longitude_deg,
            self.reference_altitude_m,
        )

    def polar_to_enu(
        self,
        range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
        radar_position_lla: Tuple[float, float, float],
        orientation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        apply_earth_curvature: bool = True,
    ) -> Tuple[float, float, float]:
        return polar_to_enu(
            range_m=range_m,
            azimuth_deg=azimuth_deg,
            elevation_deg=elevation_deg,
            radar_latitude_deg=radar_position_lla[0],
            radar_longitude_deg=radar_position_lla[1],
            radar_altitude_m=radar_position_lla[2],
            reference_latitude_deg=self.reference_latitude_deg,
            reference_longitude_deg=self.reference_longitude_deg,
            reference_altitude_m=self.reference_altitude_m,
            orientation_deg=orientation_deg,
            apply_earth_curvature=apply_earth_curvature,
        )
