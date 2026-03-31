#!/usr/bin/env python3
"""Tests for DIS protocol adapter."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.interop.dis_adapter import DISAdapter
from src.simulation.models import EntityType, SimEntity


class TestDISAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = DISAdapter(port=39999)

    def test_encode_entity_state_produces_bytes_of_expected_length(self):
        payload = self.adapter.encode_entity_state(
            {
                "entity_id": 42,
                "allegiance": "friendly",
                "entity_type": "FRIENDLY_UAV",
                "location": {"x": 100.0, "y": 200.0, "z": 50.0},
                "orientation": {"psi": 1.0, "theta": 0.1, "phi": 0.2},
                "velocity": {"x": 1.0, "y": 2.0, "z": 3.0},
            }
        )
        self.assertIsInstance(payload, bytes)
        self.assertGreater(len(payload), 40)

    def test_decode_entity_state_round_trip(self):
        entity = {
            "entity_id": 7,
            "allegiance": "enemy",
            "entity_type": "ENEMY_UAV",
            "location": {"x": 12.3, "y": 4.5, "z": 6.7},
            "orientation": {"psi": 0.3, "theta": 0.2, "phi": 0.1},
            "velocity": {"x": 9.0, "y": 8.0, "z": 7.0},
        }
        decoded = self.adapter.decode_entity_state(self.adapter.encode_entity_state(entity))
        self.assertEqual(decoded["entity_id"], 7)
        self.assertEqual(decoded["entity_type"], "ENEMY_UAV")

    def test_entity_position_preserved_through_round_trip(self):
        entity = {
            "entity_id": 11,
            "allegiance": "friendly",
            "entity_type": "FRIENDLY_UAV",
            "location": {"x": 1.25, "y": -2.5, "z": 9.75},
            "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        }
        decoded = self.adapter.decode_entity_state(self.adapter.encode_entity_state(entity))
        self.assertAlmostEqual(decoded["location"]["x"], 1.25, places=5)
        self.assertAlmostEqual(decoded["location"]["y"], -2.5, places=5)
        self.assertAlmostEqual(decoded["location"]["z"], 9.75, places=5)

    def test_force_id_mapping_friendly_enemy(self):
        friendly = self.adapter.decode_entity_state(
            self.adapter.encode_entity_state({"entity_id": 1, "allegiance": "friendly", "entity_type": "FRIENDLY_UAV"})
        )
        enemy = self.adapter.decode_entity_state(
            self.adapter.encode_entity_state({"entity_id": 2, "allegiance": "enemy", "entity_type": "ENEMY_UAV"})
        )
        self.assertEqual(friendly["force_id"], 1)
        self.assertEqual(enemy["force_id"], 2)

    def test_sim_entity_to_dis_maps_friendly_uav_correctly(self):
        sim_entity = SimEntity(
            entity_id="alpha-1",
            entity_type=EntityType.FRIENDLY_UAV,
            position=(100.0, 200.0, 50.0),
            velocity=(1.0, 2.0, 3.0),
            heading=0.5,
            health=1.0,
        )
        dis = self.adapter.sim_entity_to_dis(sim_entity)
        self.assertEqual(dis["entity_type"], "FRIENDLY_UAV")
        self.assertEqual(dis["allegiance"], "friendly")

    def test_connect_disconnect_without_network(self):
        connected = self.adapter.connect()
        self.assertIn(connected, {True, False})
        self.adapter.disconnect()
        self.assertFalse(self.adapter.connected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
