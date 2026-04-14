#!/usr/bin/env python3
"""Unit tests for radar coordinate conversion and model validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.radar.coordinate_converter import CoordinateConverter
from services.radar.models import RadarConfig, RadarPlot


class TestRadarModels(unittest.TestCase):
    def test_radar_plot_rejects_negative_range(self) -> None:
        with self.assertRaises(ValueError):
            RadarPlot(range_m=-1.0, azimuth_deg=0.0, elevation_deg=0.0)

    def test_radar_plot_rejects_invalid_elevation(self) -> None:
        with self.assertRaises(ValueError):
            RadarPlot(range_m=100.0, azimuth_deg=0.0, elevation_deg=95.0)

    def test_radar_config_validates_wgs84_bounds(self) -> None:
        with self.assertRaises(ValueError):
            RadarConfig(position=(91.0, 46.0, 500.0), uses_wgs84=True)


class TestCoordinateConverter(unittest.TestCase):
    def setUp(self) -> None:
        self.converter = CoordinateConverter()

    def test_polar_to_cartesian_north_axis(self) -> None:
        x, y, z = self.converter.polar_to_cartesian(
            range_m=1_000.0,
            azimuth_deg=0.0,
            elevation_deg=0.0,
        )
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 1_000.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)

    def test_polar_to_cartesian_applies_heading_offset(self) -> None:
        x, y, z = self.converter.polar_to_cartesian(
            range_m=2_000.0,
            azimuth_deg=0.0,
            elevation_deg=0.0,
            radar_heading_deg=90.0,
        )
        self.assertAlmostEqual(x, 2_000.0, places=6)
        self.assertAlmostEqual(y, 0.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)

    def test_curvature_and_flat_earth_differ_for_long_range(self) -> None:
        flat = self.converter.polar_to_cartesian(
            range_m=100_000.0,
            azimuth_deg=45.0,
            elevation_deg=2.0,
        )
        curved = self.converter.polar_to_cartesian_with_curvature(
            range_m=100_000.0,
            azimuth_deg=45.0,
            elevation_deg=2.0,
        )
        self.assertNotAlmostEqual(flat[2], curved[2], places=2)

    def test_wgs84_to_enu_and_back_roundtrip(self) -> None:
        ref = (24.7136, 46.6753, 600.0)
        point = (24.7145, 46.6761, 650.0)

        enu = self.converter.wgs84_to_enu(
            lat=point[0],
            lon=point[1],
            alt=point[2],
            ref_lat=ref[0],
            ref_lon=ref[1],
            ref_alt=ref[2],
        )
        lat, lon, alt = self.converter.enu_to_wgs84(
            east=enu[0],
            north=enu[1],
            up=enu[2],
            ref_lat=ref[0],
            ref_lon=ref[1],
            ref_alt=ref[2],
        )
        self.assertAlmostEqual(lat, point[0], places=6)
        self.assertAlmostEqual(lon, point[1], places=6)
        self.assertAlmostEqual(alt, point[2], places=6)

    def test_enu_to_wgs84_rejects_polar_reference(self) -> None:
        with self.assertRaises(ValueError):
            self.converter.enu_to_wgs84(
                east=10.0,
                north=10.0,
                up=10.0,
                ref_lat=90.0,
                ref_lon=0.0,
                ref_alt=0.0,
            )

    def test_convert_plot_non_wgs84(self) -> None:
        plot = RadarPlot(range_m=1_000.0, azimuth_deg=90.0, elevation_deg=0.0)
        config = RadarConfig(position=(100.0, 200.0, 10.0), heading_deg=0.0, uses_wgs84=False)

        result = self.converter.convert_plot(plot=plot, config=config, use_curvature=False)

        self.assertIs(result, plot)
        self.assertIsNotNone(result.position_cartesian)
        self.assertIsNone(result.position_wgs84)
        self.assertAlmostEqual(result.position_cartesian[0], 1_100.0, places=6)
        self.assertAlmostEqual(result.position_cartesian[1], 200.0, places=6)
        self.assertAlmostEqual(result.position_cartesian[2], 10.0, places=6)

    def test_convert_plot_wgs84_populates_cartesian_and_geodetic(self) -> None:
        plot = RadarPlot(range_m=500.0, azimuth_deg=0.0, elevation_deg=0.0)
        config = RadarConfig(position=(24.7136, 46.6753, 600.0), heading_deg=0.0, uses_wgs84=True)

        result = self.converter.convert_plot(plot=plot, config=config, use_curvature=False)

        self.assertIsNotNone(result.position_cartesian)
        self.assertIsNotNone(result.position_wgs84)
        self.assertAlmostEqual(result.position_cartesian[0], 0.0, places=6)
        self.assertAlmostEqual(result.position_cartesian[1], 500.0, places=6)
        self.assertAlmostEqual(result.position_wgs84[2], 600.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
