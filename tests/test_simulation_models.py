"""Unit tests for Layer 04 simulation data models."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.simulation.models import (
    AARReport,
    EntityType,
    ForceComposition,
    ReplayArtifact,
    ScenarioDefinition,
    SimEntity,
    SimulationState,
    SyntheticDataset,
)


def test_sim_entity_to_dict_and_distance() -> None:
    a = SimEntity(
        entity_id="a",
        entity_type=EntityType.FRIENDLY_UAV,
        position=(0.0, 0.0, 0.0),
        velocity=(1.0, 0.0, 0.0),
        heading=0.0,
        health=1.0,
        active=True,
        metadata={"role": "patrol"},
    )
    b = SimEntity(
        entity_id="b",
        entity_type=EntityType.ENEMY_UAV,
        position=(3.0, 4.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        heading=90.0,
        health=0.9,
        active=True,
        metadata={},
    )
    payload = a.to_dict()
    assert payload["entity_type"] == EntityType.FRIENDLY_UAV.value
    assert a.distance_to(b) == 5.0


def test_simulation_state_filters() -> None:
    entities = [
        SimEntity("f1", EntityType.FRIENDLY_UAV, (0.0, 0.0, 10.0), (0.0, 0.0, 0.0), 0.0, 1.0, True, {}),
        SimEntity("e1", EntityType.ENEMY_INFANTRY, (10.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0, 1.0, True, {}),
    ]
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=1.0,
        entities=entities,
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    assert state.get_entity("f1") is not None
    assert len(state.friendly_entities()) == 1
    assert len(state.enemy_entities()) == 1
    assert len(state.get_entities_by_type(EntityType.ENEMY_INFANTRY)) == 1


def test_simulation_state_to_threat_events() -> None:
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=2.0,
        entities=[
            SimEntity("e", EntityType.ENEMY_UAV, (0.0, 0.0, 100.0), (0.0, 0.0, 0.0), 0.0, 0.8, True, {})
        ],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    events = state.to_threat_events()
    assert len(events) == 1
    assert events[0].title
    assert events[0].source.value == "SENSOR_FUSION"


def test_simulation_state_to_sensor_readings() -> None:
    state = SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=3.0,
        entities=[
            SimEntity("f", EntityType.FRIENDLY_UGV, (1.0, 2.0, 0.0), (0.0, 0.0, 0.0), 90.0, 1.0, True, {})
        ],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )
    readings = state.to_sensor_readings()
    assert len(readings) == 1
    assert readings[0].sensor_id.startswith("sim-sensor-")
    assert readings[0].data["entity_id"] == "f"


def test_scenario_definition_validation() -> None:
    scenario = ScenarioDefinition(
        scenario_id="s1",
        name="Test",
        description="desc",
        scenario_type="patrol",
        terrain={"bounds": [[0, 0, 0], [100, 100, 50]]},
        weather={},
        forces=[
            ForceComposition(
                force_name="Blue",
                allegiance="friendly",
                units=[{"type": EntityType.FRIENDLY_UAV, "count": 1, "starting_position": (10, 10, 10), "behavior": "patrol"}],
            )
        ],
        objectives=[{"description": "obj", "success_condition": "True", "priority": 1}],
        rules_of_engagement="weapons_tight",
        duration_seconds=10,
        parameters={},
    )
    ok, errors = scenario.validate()
    assert ok
    assert not errors

    bad = ScenarioDefinition(
        scenario_id="s2",
        name="Bad",
        description="desc",
        scenario_type="patrol",
        terrain={"bounds": [[0, 0, 0], [100, 100, 50]]},
        weather={},
        forces=[],
        objectives=[],
        rules_of_engagement="weapons_tight",
        duration_seconds=10,
        parameters={},
    )
    ok2, errors2 = bad.validate()
    assert not ok2
    assert errors2


def test_aar_report_summary() -> None:
    aar = AARReport(
        aar_id="a1",
        scenario_id="s1",
        timestamp=datetime.now(timezone.utc),
        duration_seconds=10.0,
        outcome="victory",
        friendly_losses=1,
        enemy_losses=3,
        objectives_met=["x"],
        objectives_failed=[],
        timeline=[],
        llm_analysis=None,
        lessons_learned=[],
        statistics={},
    )
    assert "victory" in aar.summary()


def test_replay_and_dataset_models(tmp_path: Path) -> None:
    replay = ReplayArtifact(
        replay_id="r1",
        scenario_id="s1",
        simulator="builtin",
        created_at=datetime.now(timezone.utc),
        duration_seconds=1.0,
        tick_count=10,
        filepath="x.jsonl",
        file_size_bytes=128,
        metadata={},
    )
    assert replay.to_dict()["replay_id"] == "r1"

    file_path = tmp_path / "data.txt"
    file_path.write_text("abc", encoding="utf-8")
    import hashlib

    checksum = hashlib.sha256(b"abc").hexdigest()
    dataset = SyntheticDataset(
        dataset_id="d1",
        name="name",
        description="desc",
        generator="gen",
        created_at=datetime.now(timezone.utc),
        record_count=1,
        file_path=str(file_path),
        file_size_bytes=file_path.stat().st_size,
        checksum_sha256=checksum,
        schema={},
        generation_params={},
        license="S3M-INTERNAL",
    )
    assert dataset.verify_checksum()
