"""Unit tests for layered air-defense service components.

Military context:
These tests verify deterministic effector assignment, zone coverage behavior,
and safe operator input validation for tactical C2 API workflows.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.air_defense.api_routes as api_routes_module
from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import DefenseEchelon, Effector, EffectorCategory, EffectorState
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import ZoneManager


@pytest.fixture
def air_defense_module():
    """Reload module to isolate singleton route state per test."""
    return importlib.reload(api_routes_module)


@pytest.fixture
def client(air_defense_module: object) -> TestClient:
    app = FastAPI()
    app.include_router(air_defense_module.router)
    return TestClient(app)


def test_effector_registry_tracks_readiness_and_resupply():
    registry = EffectorRegistry()
    registry.register(
        Effector(
            effector_id="e-1",
            name="Test SR Battery",
            category=EffectorCategory.MISSILE,
            echelon=DefenseEchelon.SHORT_RANGE,
            position=(0.0, 0.0, 0.0),
            max_range_m=10_000.0,
            ammunition_capacity=2,
            ammunition_remaining=2,
        )
    )
    assert registry.consume_round("e-1")
    assert registry.consume_round("e-1")
    eff = registry.get("e-1")
    assert eff is not None
    assert eff.state == EffectorState.RELOADING
    assert registry.resupply("e-1", 1)
    assert eff.ammunition_remaining == 1
    assert eff.state == EffectorState.READY


def test_allocator_returns_not_allocated_without_eligible_effectors():
    registry = EffectorRegistry()
    zones = ZoneManager()
    allocator = TargetAllocator(registry, zones)
    decision = allocator.allocate("T-1", (0.0, 0.0, 0.0), 250.0, "HOSTILE_UAV")
    assert decision.allocated is False
    assert "No available effector" in decision.reasoning


def test_setup_krechet_unit_populates_effectors_and_zones(client: TestClient):
    response = client.post(
        "/air-defense/setup/krechet-unit",
        json={"center": [1_000.0, 1_000.0, 0.0], "defended_asset": "Refinery"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["effectors"] == 3
    assert payload["zones"] == 3
    assert payload["registry_stats"]["total_effectors"] == 3


def test_allocate_and_kill_flow_returns_auditable_records(client: TestClient):
    client.post("/air-defense/setup/krechet-unit", json={"center": [0.0, 0.0, 0.0]})
    allocate = client.post(
        "/air-defense/allocate",
        json={
            "target_id": "track-001",
            "position": [6_000.0, 0.0, 0.0],
            "speed_mps": 320.0,
            "classification": "HOSTILE_UAV",
        },
    )
    assert allocate.status_code == 200
    alloc_payload = allocate.json()
    assert alloc_payload["allocated"] is True
    allocation_id = alloc_payload["allocation"]["allocation_id"]
    kill = client.post("/air-defense/kill", json={"allocation_id": allocation_id})
    assert kill.status_code == 200
    assert kill.json()["status"] == "kill_confirmed"


def test_miss_endpoint_reallocates_when_possible(client: TestClient):
    client.post("/air-defense/setup/krechet-unit", json={"center": [0.0, 0.0, 0.0]})
    allocate = client.post(
        "/air-defense/allocate",
        json={"target_id": "track-002", "position": [8_000.0, 0.0, 0.0], "speed_mps": 220.0},
    )
    allocation_id = allocate.json()["allocation"]["allocation_id"]
    miss = client.post(
        "/air-defense/miss",
        json={
            "allocation_id": allocation_id,
            "updated_position": [6_500.0, 0.0, 0.0],
            "updated_speed": 260.0,
        },
    )
    assert miss.status_code == 200
    miss_payload = miss.json()
    assert "reallocated" in miss_payload
    assert "reasoning" in miss_payload


def test_allocate_requires_target_id(client: TestClient):
    response = client.post("/air-defense/allocate", json={"position": [1.0, 2.0, 3.0]})
    assert response.status_code == 400
    assert "target_id required" in response.json()["detail"]


def test_query_validation_rejects_invalid_enums(client: TestClient):
    effectors = client.get("/air-defense/effectors", params={"category": "invalid"})
    zones = client.get("/air-defense/zones", params={"echelon": "invalid"})
    assert effectors.status_code == 400
    assert zones.status_code == 400


def test_allocate_validation_rejects_invalid_position_shape(client: TestClient):
    response = client.post(
        "/air-defense/allocate",
        json={"target_id": "track-003", "position": [1.0, 2.0], "speed_mps": 120.0},
    )
    assert response.status_code == 400
    assert "3-element list" in response.json()["detail"]

