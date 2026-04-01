"""Phase-16-aligned WGS-84 conversion helpers for HLA interop."""

from __future__ import annotations

import math


class Phase16CoordinateConverter:
    """Coordinate converter numerically aligned with Phase 16 DIS formulas."""

    def __init__(self) -> None:
        self.a = 6378137.0
        self.b = 6356752.314245
        self.f = (self.a - self.b) / self.a
        self.e_sq = self.f * (2.0 - self.f)

    def lla_to_ecef(self, lat_deg: float, lon_deg: float, alt_m: float) -> tuple[float, float, float]:
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

    def ecef_to_lla(self, x: float, y: float, z: float) -> tuple[float, float, float]:
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

        for _ in range(3):
            sin_lat = math.sin(lat)
            n = self.a / math.sqrt(1.0 - self.e_sq * sin_lat * sin_lat)
            alt = p / math.cos(lat) - n
            lat = math.atan2(z, p * (1.0 - self.e_sq * n / (n + alt)))

        sin_lat = math.sin(lat)
        n = self.a / math.sqrt(1.0 - self.e_sq * sin_lat * sin_lat)
        alt = p / math.cos(lat) - n
        return (math.degrees(lat), math.degrees(lon), alt)
