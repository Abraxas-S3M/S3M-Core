"""Tests for Layer 04 replay recorder."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.simulation.adapters.replay_recorder import ReplayRecorder
from src.simulation.models import EntityType, SimEntity, SimulationState


def _state(sim_t: float) -> SimulationState:
    return SimulationState(
        timestamp=datetime.now(timezone.utc),
        sim_time_seconds=sim_t,
        entities=[
            SimEntity(
                entity_id="ent-1",
                entity_type=EntityType.FRIENDLY_UAV,
                position=(1.0, 2.0, 3.0),
                velocity=(0.0, 0.0, 0.0),
                heading=0.0,
                health=1.0,
                active=True,
                metadata={},
            )
        ],
        terrain={},
        weather={},
        active_events=[],
        metadata={},
    )


def test_start_recording_creates_file(tmp_path):
    recorder = ReplayRecorder(output_dir=str(tmp_path))
    replay_id = recorder.start_recording("builtin", "scenario-x")
    file_path = tmp_path / f"{replay_id}.jsonl"
    assert replay_id
    assert file_path.exists()


def test_record_tick_appends_file(tmp_path):
    recorder = ReplayRecorder(output_dir=str(tmp_path))
    replay_id = recorder.start_recording("builtin")
    file_path = tmp_path / f"{replay_id}.jsonl"
    recorder.record_tick(_state(0.1))
    recorder.record_tick(_state(0.2))
    text = file_path.read_text(encoding="utf-8")
    assert len([line for line in text.splitlines() if line.strip()]) == 2


def test_stop_recording_returns_artifact(tmp_path):
    recorder = ReplayRecorder(output_dir=str(tmp_path))
    replay_id = recorder.start_recording("builtin", "scenario-a")
    recorder.record_tick(_state(0.0))
    recorder.record_tick(_state(1.0))
    artifact = recorder.stop_recording()
    assert artifact.replay_id == replay_id
    assert artifact.tick_count == 2
    assert artifact.duration_seconds >= 1.0
    assert (tmp_path / f"{replay_id}.meta.json").exists()


def test_load_replay_yields_states(tmp_path):
    recorder = ReplayRecorder(output_dir=str(tmp_path))
    replay_id = recorder.start_recording("builtin")
    recorder.record_tick(_state(0.1))
    recorder.record_tick(_state(0.2))
    recorder.stop_recording()

    loaded = list(recorder.load_replay(replay_id))
    assert len(loaded) == 2
    assert all(isinstance(item, SimulationState) for item in loaded)


def test_list_replays_finds_recorded(tmp_path):
    recorder = ReplayRecorder(output_dir=str(tmp_path))
    replay_id = recorder.start_recording("builtin")
    recorder.record_tick(_state(0.0))
    recorder.stop_recording()

    listed = recorder.list_replays()
    ids = {artifact.replay_id for artifact in listed}
    assert replay_id in ids
