"""WGS-84 coordinate conversion utilities for DIS geocentric exchange."""

from __future__ import annotations

import math

from services.interop.models import DISOrientation, DISWorldCoordinate


class DISCoordinateConverter:
    """Converts between local, geodetic, and DIS ECEF coordinate spaces."""

    def __init__(self) -> None:
        self.a = 6378137.0
        self.b = 6356752.314245
        self.f = (self.a - self.b) / self.a
        self.e_sq = self.f * (2.0 - self.f)

    def lla_to_ecef(self, lat_deg: float, lon_deg: float, alt_m: float) -> tuple:
        lat = math.radians(lat_deg)
        lon = math.radians(lon_deg)
        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        sin_lon = math.sin(lon)
        cos_lon = math.cos(lon)
        n = self.a / math.sqrt(1.0 - self.e_sq * sin_lat * sin_lat)
        x = (n + alt_m) * cos_lat * cos_lon
        y = (n + alt_m) * cos_lat * sin_lon
        z = (n * (1.0 - self.e_sq) + alt_m) * sin_lat
        return (x, y, z)

    def ecef_to_lla(self, x: float, y: float, z: float) -> tuple:
        lon = math.atan2(y, x)
        p = math.sqrt(x * x + y * y)
        if p < 1e-8:
            lat = math.copysign(math.pi / 2.0, z)
            alt = abs(z) - self.b
            return (math.degrees(lat), math.degrees(lon), alt)

        ep_sq = (self.a * self.a - self.b * self.b) / (self.b * self.b)
        theta = math.atan2(z * self.a, p * self.b)
        lat = math.atan2(
            z + ep_sq * self.b * (math.sin(theta) ** 3),
            p - self.e_sq * self.a * (math.cos(theta) ** 3),
        )

        # Tactical georegistration note: Bowring iterations keep map overlays
        # stable for coalition COP alignment over long exercise windows.
        for _ in range(3):
            sin_lat = math.sin(lat)
            n = self.a / math.sqrt(1.0 - self.e_sq * sin_lat * sin_lat)
            alt = p / math.cos(lat) - n
            lat = math.atan2(z, p * (1.0 - self.e_sq * n / (n + alt)))

        sin_lat = math.sin(lat)
        n = self.a / math.sqrt(1.0 - self.e_sq * sin_lat * sin_lat)
        alt = p / math.cos(lat) - n
        return (math.degrees(lat), math.degrees(lon), alt)

    def lla_to_dis(self, lat_deg: float, lon_deg: float, alt_m: float) -> DISWorldCoordinate:
        x, y, z = self.lla_to_ecef(lat_deg, lon_deg, alt_m)
        return DISWorldCoordinate(x=x, y=y, z=z)

    def dis_to_lla(self, coord: DISWorldCoordinate) -> tuple:
        return self.ecef_to_lla(coord.x, coord.y, coord.z)

    def local_to_ecef(
        self,
        x_east: float,
        y_north: float,
        z_up: float,
        origin_lat: float,
        origin_lon: float,
        origin_alt: float,
    ) -> tuple:
        ox, oy, oz = self.lla_to_ecef(origin_lat, origin_lon, origin_alt)
        lat = math.radians(origin_lat)
        lon = math.radians(origin_lon)
        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        sin_lon = math.sin(lon)
        cos_lon = math.cos(lon)
        dx = -sin_lon * x_east - sin_lat * cos_lon * y_north + cos_lat * cos_lon * z_up
        dy = cos_lon * x_east - sin_lat * sin_lon * y_north + cos_lat * sin_lon * z_up
        dz = cos_lat * y_north + sin_lat * z_up
        return (ox + dx, oy + dy, oz + dz)

    def ecef_to_local(
        self,
        x: float,
        y: float,
        z: float,
        origin_lat: float,
        origin_lon: float,
        origin_alt: float,
    ) -> tuple:
        ox, oy, oz = self.lla_to_ecef(origin_lat, origin_lon, origin_alt)
        dx = x - ox
        dy = y - oy
        dz = z - oz
        lat = math.radians(origin_lat)
        lon = math.radians(origin_lon)
        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        sin_lon = math.sin(lon)
        cos_lon = math.cos(lon)
        east = -sin_lon * dx + cos_lon * dy
        north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
        up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
        return (east, north, up)

    def heading_to_dis_orientation(
        self,
        heading_deg: float,
        pitch_deg: float = 0,
        roll_deg: float = 0,
        lat_deg: float = 0,
        lon_deg: float = 0,
    ) -> DISOrientation:
        _ = (lat_deg, lon_deg)  # reserved for future geodesic heading compensation
        psi = math.radians(heading_deg)
        theta = math.radians(pitch_deg)
        phi = math.radians(roll_deg)
        return DISOrientation(psi=psi, theta=theta, phi=phi)
