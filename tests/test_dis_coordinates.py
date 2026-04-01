#!/usr/bin/env python3
"""Tests for DIS WGS-84 coordinate conversion utilities."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.interop.dis.coordinate_converter import DISCoordinateConverter


class TestDISCoordinates(unittest.TestCase):
    def setUp(self):
        self.conv = DISCoordinateConverter()

    def test_lla_to_ecef_riyadh_valid(self):
        x, y, z = self.conv.lla_to_ecef(24.7136, 46.6753, 0.0)
        self.assertIsInstance(x, float)
        self.assertIsInstance(y, float)
        self.assertIsInstance(z, float)
        self.assertNotEqual((x, y, z), (0.0, 0.0, 0.0))

    def test_ecef_to_lla_roundtrip_within_1m(self):
        lat, lon, alt = 24.7136, 46.6753, 0.0
        x, y, z = self.conv.lla_to_ecef(lat, lon, alt)
        r_lat, r_lon, r_alt = self.conv.ecef_to_lla(x, y, z)
        x2, y2, z2 = self.conv.lla_to_ecef(r_lat, r_lon, r_alt)
        err = ((x - x2) ** 2 + (y - y2) ** 2 + (z - z2) ** 2) ** 0.5
        self.assertLess(err, 1.0)

    def test_lla_to_ecef_mecca_valid(self):
        x, y, z = self.conv.lla_to_ecef(21.4225, 39.8262, 0.0)
        self.assertIsInstance(x, float)
        self.assertIsInstance(y, float)
        self.assertIsInstance(z, float)
        self.assertNotEqual((x, y, z), (0.0, 0.0, 0.0))

    def test_equator_prime_meridian_reference(self):
        x, y, z = self.conv.lla_to_ecef(0.0, 0.0, 0.0)
        self.assertAlmostEqual(x, self.conv.a, places=3)
        self.assertAlmostEqual(y, 0.0, places=3)
        self.assertAlmostEqual(z, 0.0, places=3)

    def test_heading_to_dis_orientation_zero_heading(self):
        orientation = self.conv.heading_to_dis_orientation(0.0)
        self.assertAlmostEqual(orientation.psi, 0.0, places=6)
        self.assertAlmostEqual(orientation.theta, 0.0, places=6)
        self.assertAlmostEqual(orientation.phi, 0.0, places=6)

    def test_local_to_ecef_and_back_roundtrip(self):
        origin_lat, origin_lon, origin_alt = 24.7136, 46.6753, 600.0
        local = (100.0, 50.0, 10.0)
        x, y, z = self.conv.local_to_ecef(*local, origin_lat, origin_lon, origin_alt)
        rx, ry, rz = self.conv.ecef_to_local(x, y, z, origin_lat, origin_lon, origin_alt)
        self.assertAlmostEqual(local[0], rx, places=1)
        self.assertAlmostEqual(local[1], ry, places=1)
        self.assertAlmostEqual(local[2], rz, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
