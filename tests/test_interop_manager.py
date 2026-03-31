#!/usr/bin/env python3
"""Unit tests for InteropManager."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.interop import InteropManager


class TestInteropManager(unittest.TestCase):
    def test_enable_protocol_for_dis(self):
        manager = InteropManager()
        ok = manager.enable_protocol("dis", {"port": 3999})
        self.assertIn(ok, {True, False})
        status = manager.get_protocol_status()
        self.assertTrue(status["dis"]["enabled"])
        manager.disable_protocol("dis")

    def test_disable_protocol(self):
        manager = InteropManager()
        manager.enable_protocol("bml")
        manager.disable_protocol("bml")
        self.assertFalse(manager.get_protocol_status()["bml"]["enabled"])

    def test_get_protocol_status_states(self):
        manager = InteropManager()
        status = manager.get_protocol_status()
        self.assertIn("dis", status)
        self.assertIn("c2sim", status)
        self.assertIn("bml", status)

    def test_send_entity_update_routes_to_enabled_only(self):
        manager = InteropManager()
        manager.enable_protocol("bml")
        result = manager.send_entity_update({"entity_id": 1, "entity_type": "FRIENDLY_UAV"})
        self.assertIn("dis", result)
        self.assertIn("c2sim", result)
        self.assertFalse(result["dis"])
        self.assertFalse(result["c2sim"])

    def test_receive_all_no_protocols_enabled_returns_empty(self):
        manager = InteropManager()
        messages = manager.receive_all()
        self.assertEqual(messages, [])

    def test_health_check_reports_all_protocols(self):
        manager = InteropManager()
        health = manager.health_check()
        self.assertEqual(health["status"], "operational")
        self.assertIn("protocols", health)
        self.assertIn("dis", health["protocols"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
