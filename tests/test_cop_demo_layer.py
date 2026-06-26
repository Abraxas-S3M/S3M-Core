"""Unit tests for the S3M-Core C4ISR/COP demonstration layer.

Tactical context:
    These tests lock down the deterministic demo scenario, the open C4ISR
    adapter seam, the AI-ready event bus, and the deterministic WebSocket motion
    so partner demonstrations (saudi_mod primary; lockheed/afrl/rsadf/golden_dome
    future-safe tracks) stay stable and repeatable. No live LLM, training, sync,
    or R2 credential path is exercised.
"""

from __future__ import annotations

import asyncio

import pytest

from src.cop.adapters.open_c4isr_adapter import OpenC4ISRAdapter
from src.cop.cop_models import CopState, CopTrack
from src.cop.cop_service import CopService
from src.cop.demo_tracks import DEMO_TRACKS, THEATER_BOUNDS, build_scenario
from src.cop.event_bus import CopEvent, CopEventBus, build_event, get_event_bus


# ── Demo scenario seed ───────────────────────────────────────

def test_demo_tracks_includes_future_safe_identifiers() -> None:
    assert DEMO_TRACKS[0] == "saudi_mod"
    for track in ("lockheed_demo", "afrl_demo", "rsadf_demo", "golden_dome_demo"):
        assert track in DEMO_TRACKS


@pytest.mark.parametrize("track", list(DEMO_TRACKS))
def test_build_scenario_is_valid_cop_state(track: str) -> None:
    scenario = build_scenario(track)
    payload = scenario.to_payload()
    payload["timestamp"] = "2026-01-01T00:00:00+00:00"
    payload["backend_health"] = {}
    payload["data_source"] = "test"
    state = CopState(**payload)
    assert state.track == track
    assert state.theater.center == [24.7136, 46.6753]
    assert state.theater.bounds == [[15.5, 34.0], [32.8, 56.8]]


def test_demo_scenario_covers_required_multi_domain_objects() -> None:
    scenario = build_scenario("saudi_mod")
    domains = {t.domain for t in scenario.tactical_tracks}
    affiliations = {t.affiliation for t in scenario.tactical_tracks}
    assert {"air", "maritime", "isr", "cyber", "missile", "sensor"}.issubset(domains)
    assert {"friendly", "hostile", "unknown"}.issubset(affiliations)
    # Hostile contacts must carry threat scoring and link to alerts.
    hostiles = [t for t in scenario.tactical_tracks if t.affiliation == "hostile"]
    assert hostiles
    for hostile in hostiles:
        assert hostile.threat_score is not None
        assert hostile.linked_alert_ids


def test_demo_decision_cards_match_required_set() -> None:
    titles = [d.title for d in build_scenario("saudi_mod").decisions]
    assert "Recommend increased monitoring of unknown air object" in titles
    assert "Recommend cueing ISR coverage toward Gulf approach" in titles
    assert "Recommend maritime escort adjustment near Hormuz" in titles
    assert "Recommend cyber watch elevation for C2 subnet anomaly" in titles
    assert "Recommend commander review before escalation" in titles
    assert "No autonomous action taken" in titles


# ── Open C4ISR adapter seam ──────────────────────────────────

def test_adapter_health_reports_demo_mode_without_live_integration() -> None:
    health = OpenC4ISRAdapter().health()
    assert health["status"] == "operational"
    assert health["mode"] == "deterministic_demo"
    assert health["live_integration"] is False


def test_adapter_fetches_demo_rows() -> None:
    adapter = OpenC4ISRAdapter()
    assert adapter.fetch_tracks("saudi_mod")
    assert adapter.fetch_alerts("saudi_mod")
    assert adapter.fetch_feed("saudi_mod")
    assert adapter.fetch_tracks("not_a_track") == []


def test_adapter_normalizes_loose_tak_style_track() -> None:
    adapter = OpenC4ISRAdapter()
    raw = {
        "uid": "TAK-1",
        "type": "uav",
        "identity": "h",
        "lat": 26.0,
        "lon": 53.0,
        "hae": 1500,
        "course": 270,
        "speed": 300,
        "threat_score": "0.9",
        "linked_alert_ids": ["alt-air-threat-003"],
    }
    track = adapter.normalize_track(raw)
    assert isinstance(track, CopTrack)
    assert track.track_id == "TAK-1"
    assert track.domain == "air"
    assert track.affiliation == "hostile"
    assert track.heading_deg == 270.0
    assert track.threat_score == 0.9
    assert track.linked_alert_ids == ["alt-air-threat-003"]


# ── AI-ready event bus ───────────────────────────────────────

def test_build_event_is_deterministic_with_explicit_id() -> None:
    event = build_event(
        track="saudi_mod",
        event_type="track_update",
        payload={"track_id": "trk-1"},
        route_hint="tactical",
        confidence=0.8,
        event_id="evt-fixed",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert isinstance(event, CopEvent)
    assert event.event_id == "evt-fixed"
    assert event.ai_context.route_hint == "tactical"
    assert event.ai_context.requires_human_review is True


def test_event_bus_publish_and_recent_are_bounded() -> None:
    bus = CopEventBus(max_events_per_track=3)
    for i in range(5):
        bus.emit(track="saudi_mod", event_type="track_update", event_id=f"e{i}", created_at=f"t{i}")
    recent = bus.recent("saudi_mod")
    assert [e.event_id for e in recent] == ["e2", "e3", "e4"]
    assert bus.recent("other_track") == []


def test_invalid_event_type_and_route_hint_fall_back_safely() -> None:
    event = build_event(track="t", event_type="bogus", route_hint="bogus")
    assert event.event_type == "track_update"
    assert event.ai_context.route_hint == "tactical"


def test_get_event_bus_is_singleton() -> None:
    assert get_event_bus() is get_event_bus()


# ── Service: tracks, bounds, determinism, event bus wiring ───

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_service_supports_all_demo_tracks() -> None:
    service = CopService()
    for track in DEMO_TRACKS:
        state = _run(service.get_state(track))
        assert state.track == track


def test_service_rejects_unknown_track() -> None:
    service = CopService()
    with pytest.raises(ValueError):
        _run(service.get_state("not_real"))


def test_websocket_motion_is_deterministic_and_bounded() -> None:
    service = CopService()
    first = _run(service.build_websocket_events("saudi_mod", 1))
    second = _run(service.build_websocket_events("saudi_mod", 1))

    cop_first = next(e for e in first if e["type"] == "cop_update")
    cop_second = next(e for e in second if e["type"] == "cop_update")
    positions_first = [(t["track_id"], t["latitude"], t["longitude"]) for t in cop_first["state"]["tactical_tracks"]]
    positions_second = [(t["track_id"], t["latitude"], t["longitude"]) for t in cop_second["state"]["tactical_tracks"]]
    assert positions_first == positions_second

    (min_lat, min_lon), (max_lat, max_lon) = THEATER_BOUNDS
    for _tid, lat, lon in positions_first:
        assert min_lat <= lat <= max_lat
        assert min_lon <= lon <= max_lon


def test_websocket_publishes_events_to_bus() -> None:
    bus = CopEventBus()
    service = CopService(event_bus=bus)
    _run(service.build_websocket_events("saudi_mod", 0))
    events = bus.recent("saudi_mod", limit=200)
    assert events
    event_types = {e.event_type for e in events}
    assert "track_update" in event_types
    assert {"alert", "decision_request"}.issubset(event_types)
    # The bridge must never auto-execute: human review stays required for threats.
    for event in events:
        if event.event_type in {"alert", "decision_request"}:
            assert event.ai_context.requires_human_review is True


def test_stationary_assets_do_not_drift() -> None:
    service = CopService()
    events = _run(service.build_websocket_events("saudi_mod", 7))
    cop = next(e for e in events if e["type"] == "cop_update")
    sensor = next(t for t in cop["state"]["tactical_tracks"] if t["track_id"] == "trk-sensor-radar-050")
    assert sensor["latitude"] == 26.42
    assert sensor["longitude"] == 50.09
