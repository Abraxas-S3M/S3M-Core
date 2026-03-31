#!/usr/bin/env python3
"""Unit tests for C2SIMAdapter."""

import os
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.interop.c2sim_adapter import C2SIMAdapter


@dataclass
class _Mission:
    mission_id: str
    mission_type: str
    waypoints: List[dict]
    rules_of_engagement: str
    agent_ids: List[str] = field(default_factory=list)


@dataclass
class _AAR:
    outcome: str = "victory"
    friendly_losses: int = 1
    enemy_losses: int = 3
    objectives_met: List[str] = field(default_factory=lambda: ["secure-zone"])
    objectives_failed: List[str] = field(default_factory=list)
    timeline: List[dict] = field(default_factory=lambda: [{"t": 1, "event": "contact"}])


class TestC2SIMAdapter(unittest.TestCase):
    def test_mission_to_order_generates_valid_xml(self):
        adapter = C2SIMAdapter()
        mission = _Mission(
            mission_id="m-1",
            mission_type="PATROL",
            waypoints=[{"x": 1, "y": 2, "z": 3}],
            rules_of_engagement="ROE-A",
            agent_ids=["u1", "u2"],
        )
        xml = adapter.mission_to_order(mission)
        self.assertIn("<Order", xml)
        self.assertIn("<OrderID>m-1</OrderID>", xml)
        self.assertIn("<TaskingOrder>", xml)

    def test_order_to_mission_round_trip(self):
        adapter = C2SIMAdapter()
        mission = _Mission(
            mission_id="m-2",
            mission_type="RECON",
            waypoints=[{"x": 10, "y": 20, "z": 5}],
            rules_of_engagement="ROE-B",
            agent_ids=["r1"],
        )
        xml = adapter.mission_to_order(mission)
        parsed = adapter.order_to_mission(xml)
        self.assertEqual(parsed["mission_type"], "RECON")
        self.assertEqual(parsed["assigned_agents"], ["r1"])
        self.assertEqual(parsed["waypoints"][0]["x"], 10.0)

    def test_aar_to_report_generates_xml(self):
        adapter = C2SIMAdapter()
        xml = adapter.aar_to_report(_AAR())
        self.assertIn("<Report", xml)
        self.assertIn("<Outcome>victory</Outcome>", xml)

    def test_offline_mode_saves_to_outbox_directory(self):
        with TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                adapter = C2SIMAdapter(server_url=None)
                ok = adapter.send_message("<Order/>")
                self.assertTrue(ok)
                outbox = Path("data/interop/c2sim_outbox")
                self.assertTrue(outbox.exists())
                self.assertGreaterEqual(len(list(outbox.glob("*.xml"))), 1)
            finally:
                os.chdir(cwd)

    def test_get_message_log_returns_entries(self):
        adapter = C2SIMAdapter(server_url=None)
        adapter.send_message("<Order/>")
        log = adapter.get_message_log(limit=20)
        self.assertGreaterEqual(len(log), 1)
        self.assertEqual(log[-1]["direction"], "outbound")


if __name__ == "__main__":
    unittest.main(verbosity=2)
