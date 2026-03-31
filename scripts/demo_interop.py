#!/usr/bin/env python3
"""Interoperability demo for S3M Phase 10 protocols."""

from __future__ import annotations

import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List

from src.security.interop import C2SIMAdapter, DISAdapter, InteropManager


@dataclass
class _DemoEntity:
    entity_id: str
    entity_type: str
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    heading: float


@dataclass
class _MissionType:
    value: str


@dataclass
class _DemoMission:
    mission_id: str
    mission_type: _MissionType
    agent_ids: List[str]
    waypoints: List[dict]
    rules_of_engagement: str


def _print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def main() -> int:
    _print_section("S3M PHASE 10 - INTEROPERABILITY DEMO")
    manager = InteropManager()
    dis_enabled = manager.enable_protocol("dis", {"port": 3000, "broadcast_address": "255.255.255.255"})
    print(f"DIS enabled: {dis_enabled}")

    entity = _DemoEntity(
        entity_id="friendly-uav-1",
        entity_type="FRIENDLY_UAV",
        position=(100.0, 200.0, 50.0),
        velocity=(5.0, 0.0, 0.0),
        heading=1.57,
    )
    dis = DISAdapter()
    dis_dict = dis.sim_entity_to_dis(entity)
    encoded = dis.encode_entity_state(dis_dict)
    decoded = dis.decode_entity_state(encoded)

    _print_section("DIS ENTITY STATE PDU")
    print(f"Encoded bytes length: {len(encoded)}")
    print(f"PDU hex dump (first 120 chars): {binascii.hexlify(encoded).decode('ascii')[:120]}...")
    print("Decoded entity:")
    print(decoded)
    print("Round-trip position preserved:", decoded["location"])

    mission = _DemoMission(
        mission_id="mission-demo-001",
        mission_type=_MissionType("PATROL"),
        agent_ids=["uav-1", "uav-2"],
        waypoints=[
            {"x": 100.0, "y": 200.0, "z": 50.0},
            {"x": 120.0, "y": 250.0, "z": 55.0},
            {"x": 90.0, "y": 260.0, "z": 45.0},
        ],
        rules_of_engagement="HOLD_FIRE_UNLESS_FIRED_UPON",
    )
    c2sim = C2SIMAdapter()
    order_xml = c2sim.mission_to_order(mission)
    mission_back = c2sim.order_to_mission(order_xml)

    _print_section("C2SIM ORDER ROUND-TRIP")
    print(order_xml)
    print("\nParsed mission dict:")
    print(mission_back)

    _print_section("BML SITREP GENERATION")
    bml = manager.bml_adapter
    events: List[Any] = [
        {
            "source": "ThreatManager",
            "event_type": "ENEMY_UAV_DETECTED",
            "location": {"x": 500.0, "y": 600.0, "z": 120.0},
            "event_time": datetime.now(timezone.utc).isoformat(),
        },
        {
            "source": "SensorFusion",
            "event_type": "RADAR_CONTACT",
            "location": {"x": 505.0, "y": 602.0, "z": 118.0},
            "event_time": datetime.now(timezone.utc).isoformat(),
        },
    ]
    sitrep = bml.generate_report(events, report_type="SITREP")
    print(sitrep)

    _print_section("PROTOCOL STATUS SUMMARY")
    print(manager.get_protocol_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
