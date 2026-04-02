"""Smoke tests for S3M gap-closure integration modules."""

from __future__ import annotations

import unittest

from src.command import MissionCommandEngine
from src.force_awareness import ForceAwarenessManager
from src.logistics import SupplyChainTwin
from src.planning import MultiDomainMissionPlanner


class TestGapClosureSmoke(unittest.TestCase):
    """Ensure new gap-closure modules instantiate and run minimally."""

    def test_mission_command_engine_smoke(self) -> None:
        engine = MissionCommandEngine()
        result = engine.issue_command(
            {
                "mission_brief": "Assess sector delta and recommend posture.",
                "requested_action": "ASSESS",
            }
        )
        self.assertIn("action", result)
        self.assertIn("recommendation_text", result)
        self.assertIn("confidence", result)

    def test_force_awareness_manager_smoke(self) -> None:
        manager = ForceAwarenessManager()
        result = manager.ingest_tracks(
            [
                {
                    "unit_id": "blue-1",
                    "role": "recon",
                    "status": "active",
                    "position": [10.0, 20.0, 5.0],
                }
            ]
        )
        self.assertEqual(result["accepted"], 1)
        self.assertGreaterEqual(result["track_count"], 1)

    def test_supply_chain_twin_smoke(self) -> None:
        twin = SupplyChainTwin()
        prediction = twin.predict_disruptions(
            [
                {
                    "id": "shipment-1",
                    "delay_hours": 2.0,
                    "weight": 100.0,
                    "priority": 3,
                    "route_distance": 250.0,
                    "origin": "alpha",
                    "dest": "bravo",
                }
            ]
        )
        self.assertIn("total_shipments", prediction)
        self.assertIn("overall_risk", prediction)

    def test_multi_domain_mission_planner_smoke(self) -> None:
        planner = MultiDomainMissionPlanner()
        plan = planner.plan(
            {
                "mission_type": "PATROL",
                "waypoints": [(0.0, 0.0, 20.0), (100.0, 50.0, 25.0)],
                "num_agents": 1,
                "rules_of_engagement": "weapons_tight",
            }
        )
        self.assertIn("mission_id", plan)
        self.assertEqual(plan["mission_type"], "PATROL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
