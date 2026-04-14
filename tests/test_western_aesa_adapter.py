"""Unit tests for Western AESA radar adapter behavior."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from services.radar.adapters.western_aesa_adapter import WesternAESAAdapter
from services.radar.models import RadarBand, RadarType, ScanMode


class TestWesternAESAAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = WesternAESAAdapter()

    def test_parse_single_payload_uses_range_km_and_bearing_fallbacks(self) -> None:
        plots = self.adapter.parse_raw_data(
            {
                "timestamp": "2026-04-14T10:00:00+00:00",
                "range_km": 12.5,
                "bearing_deg": 42.0,
                "radial_velocity_mps": -115.5,
            }
        )

        self.assertEqual(len(plots), 1)
        self.assertEqual(plots[0].radar_id, self.adapter.config.radar_id)
        self.assertEqual(plots[0].timestamp, datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(plots[0].range_m, 12_500.0)
        self.assertEqual(plots[0].azimuth_deg, 42.0)
        self.assertEqual(plots[0].radial_velocity_mps, -115.5)
        self.assertEqual(plots[0].snr_db, 25.0)

    def test_parse_detections_list(self) -> None:
        plots = self.adapter.parse_raw_data(
            {
                "detections": [
                    {"range_m": 1000.0, "azimuth_deg": 5.0},
                    {"range_m": 2000.0, "azimuth_deg": 15.0},
                ]
            }
        )
        self.assertEqual(len(plots), 2)
        self.assertEqual(plots[0].range_m, 1000.0)
        self.assertEqual(plots[1].azimuth_deg, 15.0)

    def test_default_config_matches_western_aesa_profile(self) -> None:
        cfg = self.adapter.create_default_config()
        self.assertEqual(cfg.radar_type, RadarType.AESA_WESTERN)
        self.assertEqual(cfg.band, RadarBand.C_BAND)
        self.assertEqual(cfg.scan_mode, ScanMode.ELECTRONIC)
        self.assertEqual(cfg.max_range_m, 75_000)
        self.assertTrue(cfg.has_doppler)


if __name__ == "__main__":
    unittest.main(verbosity=2)

