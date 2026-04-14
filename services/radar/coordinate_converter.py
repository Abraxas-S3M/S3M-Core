"""Polar-to-Cartesian coordinate conversion for radar plots.

Military context:
Radars natively output detections in polar coordinates (range, azimuth, elevation)
relative to the radar's position. The Krechet 9C905 converts plots from every
radar into a common Cartesian reference frame before fusion. This module provides
that conversion, including optional WGS84 geodetic to local ENU transformation.
"""

from __future__ import annotations

import math
from typing import Tuple

from services.radar.models import RadarConfig, RadarPlot


class CoordinateConverter:
    """Convert radar polar measurements to Cartesian coordinates."""

    EARTH_RADIUS_M = 6_371_000.0

    @staticmethod
    def _require_finite(value: float, name: str) -> None:
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number")

    @classmethod
    def _validate_polar_inputs(
        cls,
        range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
        radar_position: Tuple[float, float, float],
        radar_heading_deg: float,
    ) -> None:
        cls._require_finite(range_m, "range_m")
        cls._require_finite(azimuth_deg, "azimuth_deg")
        cls._require_finite(elevation_deg, "elevation_deg")
        cls._require_finite(radar_heading_deg, "radar_heading_deg")
        if range_m < 0.0:
            raise ValueError("range_m must be >= 0")
        if not -90.0 <= elevation_deg <= 90.0:
            raise ValueError("elevation_deg must be between -90 and 90")
        if len(radar_position) != 3:
            raise ValueError("radar_position must be a 3-tuple")
        cls._require_finite(radar_position[0], "radar_position[0]")
        cls._require_finite(radar_position[1], "radar_position[1]")
        cls._require_finite(radar_position[2], "radar_position[2]")

    @staticmethod
    def polar_to_cartesian(
        range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
        radar_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        radar_heading_deg: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Convert a single polar measurement to Cartesian (x, y, z).

        Convention:
        - x: East
        - y: North
        - z: Up
        - Azimuth: 0 = North, clockwise
        """
        CoordinateConverter._validate_polar_inputs(
            range_m,
            azimuth_deg,
            elevation_deg,
            radar_position,
            radar_heading_deg,
        )
        true_azimuth = (azimuth_deg + radar_heading_deg) % 360.0
        az_rad = math.radians(true_azimuth)
        el_rad = math.radians(elevation_deg)

        # Tactical context: This is the standard flat-Earth conversion used for
        # short-range track files where curvature error is below operator tolerance.
        ground_range = range_m * math.cos(el_rad)
        height = range_m * math.sin(el_rad)

        east = ground_range * math.sin(az_rad)
        north = ground_range * math.cos(az_rad)
        up = height

        x = radar_position[0] + east
        y = radar_position[1] + north
        z = radar_position[2] + up

        return (x, y, z)

    @classmethod
    def polar_to_cartesian_with_curvature(
        cls,
        range_m: float,
        azimuth_deg: float,
        elevation_deg: float,
        radar_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        radar_heading_deg: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Polar to Cartesian with Earth curvature correction for long-range radars.

        For ranges > 20km, the flat-Earth approximation introduces non-trivial
        altitude error. This uses the 4/3 Earth radius model standard in radar
        engineering for refraction-corrected height calculation.
        """
        cls._validate_polar_inputs(
            range_m,
            azimuth_deg,
            elevation_deg,
            radar_position,
            radar_heading_deg,
        )
        effective_earth_radius = cls.EARTH_RADIUS_M * (4.0 / 3.0)
        true_azimuth = (azimuth_deg + radar_heading_deg) % 360.0
        az_rad = math.radians(true_azimuth)
        el_rad = math.radians(elevation_deg)

        height = (
            math.sqrt(
                range_m * range_m
                + effective_earth_radius * effective_earth_radius
                + 2.0 * range_m * effective_earth_radius * math.sin(el_rad)
            )
            - effective_earth_radius
        )

        asin_arg = (range_m * math.cos(el_rad)) / (effective_earth_radius + height)
        asin_arg = max(-1.0, min(1.0, asin_arg))
        ground_range = effective_earth_radius * math.asin(asin_arg)

        east = ground_range * math.sin(az_rad)
        north = ground_range * math.cos(az_rad)
        up = height

        x = radar_position[0] + east
        y = radar_position[1] + north
        z = radar_position[2] + up

        return (x, y, z)

    @classmethod
    def wgs84_to_enu(
        cls,
        lat: float,
        lon: float,
        alt: float,
        ref_lat: float,
        ref_lon: float,
        ref_alt: float,
    ) -> Tuple[float, float, float]:
        """Convert WGS84 geodetic to local East-North-Up (meters)."""
        for value, name in (
            (lat, "lat"),
            (lon, "lon"),
            (alt, "alt"),
            (ref_lat, "ref_lat"),
            (ref_lon, "ref_lon"),
            (ref_alt, "ref_alt"),
        ):
            cls._require_finite(value, name)
        if not -90.0 <= lat <= 90.0:
            raise ValueError("lat must be between -90 and 90")
        if not -90.0 <= ref_lat <= 90.0:
            raise ValueError("ref_lat must be between -90 and 90")
        if not -180.0 <= lon <= 180.0:
            raise ValueError("lon must be between -180 and 180")
        if not -180.0 <= ref_lon <= 180.0:
            raise ValueError("ref_lon must be between -180 and 180")

        d_lat = math.radians(lat - ref_lat)
        d_lon = math.radians(lon - ref_lon)
        cos_ref = math.cos(math.radians(ref_lat))

        east = d_lon * cls.EARTH_RADIUS_M * cos_ref
        north = d_lat * cls.EARTH_RADIUS_M
        up = alt - ref_alt

        return (east, north, up)

    @classmethod
    def enu_to_wgs84(
        cls,
        east: float,
        north: float,
        up: float,
        ref_lat: float,
        ref_lon: float,
        ref_alt: float,
    ) -> Tuple[float, float, float]:
        """Convert local ENU (meters) back to WGS84 geodetic."""
        for value, name in (
            (east, "east"),
            (north, "north"),
            (up, "up"),
            (ref_lat, "ref_lat"),
            (ref_lon, "ref_lon"),
            (ref_alt, "ref_alt"),
        ):
            cls._require_finite(value, name)
        if not -90.0 <= ref_lat <= 90.0:
            raise ValueError("ref_lat must be between -90 and 90")
        if not -180.0 <= ref_lon <= 180.0:
            raise ValueError("ref_lon must be between -180 and 180")

        cos_ref = math.cos(math.radians(ref_lat))
        if abs(cos_ref) < 1e-12:
            raise ValueError("enu_to_wgs84 is undefined at the poles")

        lat = ref_lat + math.degrees(north / cls.EARTH_RADIUS_M)
        lon = ref_lon + math.degrees(east / (cls.EARTH_RADIUS_M * cos_ref))
        alt = ref_alt + up
        return (lat, lon, alt)

    def convert_plot(
        self,
        plot: RadarPlot,
        config: RadarConfig,
        use_curvature: bool = True,
    ) -> RadarPlot:
        """Convert a RadarPlot's polar coordinates to Cartesian in-place.

        If the radar uses WGS84 positioning, first converts radar position
        to local ENU, then applies polar-to-Cartesian from there.
        """
        if not isinstance(plot, RadarPlot):
            raise TypeError("plot must be a RadarPlot")
        if not isinstance(config, RadarConfig):
            raise TypeError("config must be a RadarConfig")

        radar_pos = config.position
        if config.uses_wgs84:
            radar_pos = (0.0, 0.0, 0.0)

        if use_curvature and plot.range_m > 20_000:
            cartesian = self.polar_to_cartesian_with_curvature(
                plot.range_m,
                plot.azimuth_deg,
                plot.elevation_deg,
                radar_pos,
                config.heading_deg,
            )
        else:
            cartesian = self.polar_to_cartesian(
                plot.range_m,
                plot.azimuth_deg,
                plot.elevation_deg,
                radar_pos,
                config.heading_deg,
            )

        plot.position_cartesian = cartesian
        if config.uses_wgs84:
            plot.position_wgs84 = self.enu_to_wgs84(
                cartesian[0],
                cartesian[1],
                cartesian[2],
                config.position[0],
                config.position[1],
                config.position[2],
            )

        return plot
