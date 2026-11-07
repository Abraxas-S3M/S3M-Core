"""Lightweight Cortex integration tests (offline / fixture-only)."""

from __future__ import annotations

from packages.integrations.cyber.cortex.adapter import CortexAdapter


def test_cortex_adapter_airgapped_fixture_execute() -> None:
    adapter = CortexAdapter(mode="airgapped")
    result = adapter.execute({"action": "run_analyzer"})
    assert result["status"] == "ok"
    assert result["integration_id"] == "cortex"
    assert result["mode"] == "airgapped"
