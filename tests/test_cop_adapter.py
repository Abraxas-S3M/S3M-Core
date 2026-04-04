"""Unit tests for COP GUI bridge adapter."""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
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

    schema_mod.GUIThreatTrack = GUIThreatTrack
    schema_mod.GUITracksData = GUITracksData
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
    sys.modules.pop("src.api.gui_bridge.adapters.cop_adapter", None)
    return importlib.import_module("src.api.gui_bridge.adapters.cop_adapter")


def test_cop_adapter_maps_tracks_and_threat_tracks(monkeypatch):
    _install_gui_schema_stubs(monkeypatch)
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
    _install_gui_schema_stubs(monkeypatch)
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()

    assert adapter_module.COPAdapter._to_percent(0.5) == 50
    assert adapter_module.COPAdapter._to_percent(150) == 100
    assert adapter_module.COPAdapter._to_percent(-10) == 0
    assert adapter_module.COPAdapter._infer_domain({"type": "sigint relay"}) == "intel"
