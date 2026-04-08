"""Unit tests for COP GUI bridge adapter."""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _install_gui_schema_stubs(monkeypatch):
    schema_mod = types.ModuleType("src.api.gui_bridge.models.gui_schemas")

    @dataclass
    class GUIThreatTrack:
        id: str
        domain: str
        confidence: int
        severity: int
        correlatedTrackIds: list[str]
        summary: str
        lastSeen: str

    @dataclass
    class GUITracksData:
        tracks: list[GUIThreatTrack]
        updatedAt: str

    @dataclass
    class GUIReplayFrame:
        timestamp: str
        tracks: list[GUIThreatTrack]

    @dataclass
    class GUIMissionLayer:
        missionId: str
        waypoints: list[dict[str, Any]]
        phaseLines: list[dict[str, Any]]
        objectives: list[dict[str, Any]]

    schema_mod.GUIThreatTrack = GUIThreatTrack
    schema_mod.GUITracksData = GUITracksData
    schema_mod.GUIReplayFrame = GUIReplayFrame
    schema_mod.GUIMissionLayer = GUIMissionLayer
    monkeypatch.setitem(sys.modules, "src.api.gui_bridge.models.gui_schemas", schema_mod)
    return schema_mod


def _install_cop_provider_stub(monkeypatch) -> None:
    cop_mod = types.ModuleType("src.dashboard.providers.cop_provider")

    class COPDataProvider:
        def get_tracks(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": "TRK-1",
                    "type": "aircraft",
                    "confidence": 0.91,
                    "threat_score": 0.86,
                    "correlated": ["TRK-2"],
                    "classification": "Hostile fixed-wing",
                    "last_update": "2026-04-04T02:00:00+00:00",
                },
                {
                    "id": "TRK-3",
                    "type": "network packet stream",
                    "confidence": 64,
                    "threat_score": 120,
                    "correlated": [],
                    "classification": "Potential C2 beaconing",
                    "last_update": "2026-04-04T02:10:00+00:00",
                },
            ]

        def get_threats(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": "TH-1",
                    "level": "HIGH",
                    "category": "CYBER",
                    "confidence": 0.52,
                    "description": "Potential lateral movement indicators observed.",
                    "timestamp": "2026-04-04T02:15:00+00:00",
                }
            ]

    cop_mod.COPDataProvider = COPDataProvider
    monkeypatch.setitem(sys.modules, "src.dashboard.providers.cop_provider", cop_mod)


def _reload_cop_adapter():
    module_name = "cop_adapter_under_test"
    sys.modules.pop(module_name, None)
    adapter_path = Path(__file__).resolve().parents[1] / "src/api/gui_bridge/adapters/cop_adapter.py"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load cop adapter test module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _install_replay_stub(monkeypatch) -> None:
    replay_harness_mod = types.ModuleType("src.validation.replay_harness")

    class ReplayHarness:
        pass

    replay_harness_mod.ReplayHarness = ReplayHarness
    monkeypatch.setitem(sys.modules, "src.validation.replay_harness", replay_harness_mod)

    replay_recorder_mod = types.ModuleType("src.simulation.adapters.replay_recorder")

    @dataclass
    class ReplayArtifact:
        replay_id: str
        created_at: datetime

    class SimulationState:
        def __init__(self, ts: datetime, entities: list[dict[str, Any]]):
            self.timestamp = ts
            self._entities = entities

        def to_dict(self) -> dict[str, Any]:
            return {
                "timestamp": self.timestamp.isoformat(),
                "entities": self._entities,
            }

    class ReplayRecorder:
        def list_replays(self) -> list[ReplayArtifact]:
            return [
                ReplayArtifact(
                    replay_id="r-1",
                    created_at=datetime(2026, 4, 4, 2, 0, tzinfo=timezone.utc),
                )
            ]

        def load_replay(self, replay_id: str):
            assert replay_id == "r-1"
            return [
                SimulationState(
                    datetime(2026, 4, 4, 2, 5, tzinfo=timezone.utc),
                    [
                        {
                            "entity_id": "EN-1",
                            "entity_type": "ENEMY_UGV",
                            "health": 0.72,
                            "metadata": {"correlatedTrackIds": ["EN-2"]},
                        },
                        {
                            "entity_id": "FR-1",
                            "entity_type": "FRIENDLY_UGV",
                            "health": 0.91,
                        },
                    ],
                )
            ]

    replay_recorder_mod.ReplayRecorder = ReplayRecorder
    monkeypatch.setitem(
        sys.modules,
        "src.simulation.adapters.replay_recorder",
        replay_recorder_mod,
    )


def _install_mission_planner_stub(monkeypatch) -> None:
    mission_mod = types.ModuleType("src.planning.mission_planner")

    class MissionPlanner:
        def get_missions(self) -> list[dict[str, Any]]:
            return [
                {
                    "mission_id": "mission-123",
                    "mission_type": "RECON",
                    "status": "planned",
                    "waypoints": [(0.0, 0.0, 10.0), (100.0, 50.0, 20.0)],
                    "objectives": [{"id": "OBJ-A", "label": "observe target", "status": "planned"}],
                }
            ]

    mission_mod.MissionPlanner = MissionPlanner
    monkeypatch.setitem(sys.modules, "src.planning.mission_planner", mission_mod)


def test_cop_adapter_maps_tracks_and_threat_tracks(monkeypatch):
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()
    adapter = adapter_module.COPAdapter()

    tracks = adapter.get_tracks()
    assert len(tracks.tracks) == 2
    assert tracks.tracks[0].domain == "kinetic"
    assert tracks.tracks[0].confidence == 91
    assert tracks.tracks[0].severity == 86
    assert tracks.tracks[1].domain == "cyber"
    assert tracks.tracks[1].severity == 100

    threat_tracks = adapter.get_threat_tracks()
    assert len(threat_tracks.tracks) == 1
    assert threat_tracks.tracks[0].domain == "cyber"
    assert threat_tracks.tracks[0].confidence == 52
    assert threat_tracks.tracks[0].severity == 75


def test_cop_adapter_percent_and_domain_helpers(monkeypatch):
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()

    assert adapter_module.COPAdapter._to_percent(0.5) == 50
    assert adapter_module.COPAdapter._to_percent(150) == 100
    assert adapter_module.COPAdapter._to_percent(-10) == 0
    assert adapter_module.COPAdapter._infer_domain({"type": "sigint relay"}) == "intel"


def test_cop_adapter_get_replay_filters_window(monkeypatch):
    _install_gui_schema_stubs(monkeypatch)
    _install_cop_provider_stub(monkeypatch)
    _install_replay_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()
    adapter = adapter_module.COPAdapter()

    frames = adapter.get_replay(
        start_time="2026-04-04T01:59:00+00:00",
        end_time="2026-04-04T02:06:00+00:00",
    )

    assert len(frames) == 1
    assert frames[0]["timestamp"] == "2026-04-04T02:05:00+00:00"
    assert len(frames[0]["tracks"]) == 1
    assert frames[0]["tracks"][0].id == "EN-1"
    assert frames[0]["tracks"][0].confidence == 72


def test_cop_adapter_get_mission_overlay(monkeypatch):
    _install_gui_schema_stubs(monkeypatch)
    _install_cop_provider_stub(monkeypatch)
    _install_mission_planner_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()
    adapter = adapter_module.COPAdapter()

    overlay = adapter.get_mission_overlay(mission_id="mission-123")

    assert overlay["missionId"] == "mission-123"
    assert len(overlay["waypoints"]) == 2
    assert len(overlay["phaseLines"]) == 1
    assert overlay["objectives"][0]["id"] == "OBJ-A"
