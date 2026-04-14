"""Unit tests for radar integration demo script."""

from __future__ import annotations

import importlib
import sys


def test_demo_radar_integration_runs_and_prints_fused_air_picture(capsys) -> None:
    """Demo should show layered detections and one fused tactical track."""
    monkeypatch_module = sys.modules
    monkeypatch_module.pop("scripts.demo_radar_integration", None)

    demo_module = importlib.import_module("scripts.demo_radar_integration")
    demo_module.main()

    output = capsys.readouterr().out
    assert "S3M RADAR INTEGRATION DEMO" in output
    assert "[2] AESA detects target at 45km" in output
    assert "[3] RPS-202 detects same target at 18km" in output
    assert "[4] RPS-82 detects same target at 12km" in output
    assert "Fused tracks: 1" in output
    assert "state=confirmed" in output
    assert "Demo complete. Multi-radar air picture operational." in output
