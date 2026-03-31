#!/usr/bin/env python3
"""Unit tests for BML adapter."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.interop.bml_adapter import BMLAdapter
from src.simulation.models import AARReport
from datetime import datetime, timezone


class TestBMLAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = BMLAdapter()

    def test_parse_order_extracts_who_what_where(self):
        xml = """
        <BMLOrder>
          <Who>alpha-1</Who>
          <What>ATTACK</What>
          <Where><Coordinate><X>10</X><Y>20</Y><Z>5</Z></Coordinate></Where>
          <When>NOW</When>
          <Why>Neutralize threat</Why>
        </BMLOrder>
        """
        parsed = self.adapter.parse_order(xml)
        self.assertEqual(parsed["who"], "alpha-1")
        self.assertEqual(parsed["what"], "ENGAGE")
        self.assertEqual(parsed["where"], (10.0, 20.0, 5.0))

    def test_what_mapping_attack_to_engage_and_defend_to_hold(self):
        attack = self.adapter.parse_order("<BMLOrder><Who>a</Who><What>ATTACK</What></BMLOrder>")
        defend = self.adapter.parse_order("<BMLOrder><Who>a</Who><What>DEFEND</What></BMLOrder>")
        self.assertEqual(attack["what"], "ENGAGE")
        self.assertEqual(defend["what"], "HOLD")

    def test_generate_report_creates_valid_sitrep_xml(self):
        events = [
            {"source": "sensor", "event_type": "contact", "location": {"x": 1, "y": 2, "z": 3}, "event_time": "t0"}
        ]
        xml = self.adapter.generate_report(events, report_type="SITREP")
        self.assertIn("<BMLReport>", xml)
        self.assertIn("<ReportType>SITREP</ReportType>", xml)
        self.assertIn("<Observation>", xml)

    def test_generate_aar_report_includes_outcome_and_losses(self):
        aar = AARReport(
            aar_id="aar-1",
            scenario_id="scn-1",
            timestamp=datetime.now(timezone.utc),
            duration_seconds=10.0,
            outcome="victory",
            friendly_losses=1,
            enemy_losses=4,
            objectives_met=["obj1"],
            objectives_failed=[],
            timeline=[],
        )
        xml = self.adapter.generate_aar_report(aar)
        self.assertIn("<Outcome>victory</Outcome>", xml)
        self.assertIn("<FriendlyLosses>1</FriendlyLosses>", xml)
        self.assertIn("<EnemyLosses>4</EnemyLosses>", xml)

    def test_validate_bml_catches_missing_required_elements(self):
        ok, errors = self.adapter.validate_bml("<UnknownRoot><foo/></UnknownRoot>")
        self.assertFalse(ok)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
