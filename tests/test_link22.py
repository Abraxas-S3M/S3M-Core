"""Unit tests for Link 22 adapter stub behavior.

Military/tactical context:
These tests lock the Link 22 API contract so coalition tactical workflows can
integrate now and swap in classified parsing later without breaking interfaces.
"""

from __future__ import annotations

import importlib.util
import logging
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "services" / "interop" / "link22" / "link22_adapter.py"


def _load_link22_adapter() -> type:
    spec = importlib.util.spec_from_file_location("tests.link22_adapter", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Link22Adapter


Link22Adapter = _load_link22_adapter()


class TestLink22Adapter(unittest.TestCase):
    def test_connect_forces_stub_mode_and_returns_false(self) -> None:
        adapter = Link22Adapter({"mode": "integration"})
        with self.assertLogs(adapter.logger.name, level=logging.WARNING) as captured:
            connected = adapter.connect("239.10.22.1:5522")

        self.assertIs(connected, False)
        self.assertEqual(adapter.mode, "stub")
        self.assertTrue(
            any("Link 22 connection requires classified interface — stub mode active" in line for line in captured.output)
        )

    def test_receive_tracks_returns_empty_list_in_stub_mode(self) -> None:
        adapter = Link22Adapter({"mode": "stub"})
        self.assertEqual(adapter.receive_tracks(), [])

    def test_publish_track_logs_and_returns_false_in_stub_mode(self) -> None:
        adapter = Link22Adapter({"mode": "stub"})
        sample_track = {"id": "track-1", "entity_type": "ENEMY_UAV"}
        with self.assertLogs(adapter.logger.name, level=logging.INFO) as captured:
            published = adapter.publish_track(sample_track)

        self.assertIs(published, False)
        self.assertTrue(any("Link 22 stub publish requested for track" in line for line in captured.output))
        self.assertTrue(any("track-1" in line for line in captured.output))

    def test_supported_messages_match_stub_contract(self) -> None:
        adapter = Link22Adapter({"mode": "stub"})
        self.assertEqual(
            adapter.get_supported_messages(),
            [
                "F.1 - Unit Position",
                "F.2 - Air Track",
                "F.3 - Surface Track",
                "F.5 - EW Track",
                "F.6 - ACCS Report",
            ],
        )

    def test_health_check_reports_classified_stub_status(self) -> None:
        adapter = Link22Adapter({"mode": "stub"})
        self.assertEqual(adapter.health_check(), {"status": "stub", "reason": "Classified interface not available"})

    def test_f_series_to_s3m_entity_mapping_is_documented(self) -> None:
        adapter = Link22Adapter({"mode": "stub"})
        mapping = adapter.get_message_entity_mapping()

        self.assertEqual(mapping["F.1 - Unit Position"], ["FRIENDLY_UGV", "ENEMY_UGV"])
        self.assertEqual(mapping["F.2 - Air Track"], ["FRIENDLY_UAV", "ENEMY_UAV"])
        self.assertEqual(mapping["F.3 - Surface Track"], ["FRIENDLY_SHIP", "ENEMY_SHIP"])
        self.assertEqual(mapping["F.5 - EW Track"], ["ENEMY_UAV", "ENEMY_UGV"])
        self.assertEqual(mapping["F.6 - ACCS Report"], ["CIVILIAN", "UNKNOWN"])

    def test_input_validation_rejects_invalid_config_and_track(self) -> None:
        with self.assertRaisesRegex(ValueError, "config must be a dictionary"):
            Link22Adapter(config=None)  # type: ignore[arg-type]

        adapter = Link22Adapter({"mode": "stub"})
        with self.assertRaisesRegex(ValueError, "track must be a dictionary"):
            adapter.publish_track(track="invalid")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
