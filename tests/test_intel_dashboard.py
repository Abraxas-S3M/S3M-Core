from __future__ import annotations

from src.apps.intel.intel_manager import IntelManager


def test_get_intel_overview_returns_expected_keys() -> None:
    manager = IntelManager()
    manager.collector.source_manager.create_default_sources()
    manager.monitor.early_warning.create_default_indicators()
    overview = manager.get_intel_overview()
    for key in (
        "items_last_24h",
        "items_last_7d",
        "sources_active",
        "sources_by_type",
        "crises_active",
        "crises_by_region",
        "warnings_triggered",
        "risk_by_region",
        "top_events",
        "latest_brief",
        "collection_health",
    ):
        assert key in overview


def test_get_region_intel_returns_data() -> None:
    manager = IntelManager()
    payload = manager.get_region_intel("Persian Gulf")
    assert payload["region"] == "Persian Gulf"
    assert isinstance(payload["items"], list)
    assert isinstance(payload["crises"], list)
    assert isinstance(payload["warnings"], list)


def test_get_crisis_board_returns_status() -> None:
    manager = IntelManager()
    board = manager.dashboard.get_crisis_board()
    assert isinstance(board, list)


def test_get_source_health_returns_statuses() -> None:
    manager = IntelManager()
    manager.collector.source_manager.create_default_sources()
    rows = manager.dashboard.get_source_health()
    assert isinstance(rows, list)
    if rows:
        assert "active" in rows[0]
