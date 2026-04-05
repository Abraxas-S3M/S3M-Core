"""Unit tests for mission dashboard provider snapshots."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.mission_provider import MissionProvider
from src.dashboard.providers.runtime_store import (
    reset_runtime_state,
    set_last_swarm_command,
    set_missions,
)


def setup_function() -> None:
    reset_runtime_state()


def test_mission_snapshot_contains_phase_status_timeline_and_queue() -> None:
    set_missions(
        [
            {
                "id": "m-1",
                "status": "active",
                "phase": "transit",
                "platform_class": "ugv_wheeled",
                "risk_score": 0.12,
                "time_remaining_s": 360.0,
                "started_at": "2026-04-01T10:00:00+00:00",
            }
        ]
    )
    set_last_swarm_command({"command_id": "cmd-1", "command_type": "move_to"})

    provider = MissionProvider()
    snapshot = provider.get_snapshot()
    assert snapshot["provider"] == "mission"
    assert snapshot["mission_phase_status"]
    assert snapshot["phase_transition_timeline"]
    assert snapshot["command_queue"]
    assert snapshot["summary"]["missions"] == 1


def test_mission_snapshot_runtime_fallback_has_phase_fields() -> None:
    set_missions([{"id": "m-2", "status": "paused", "mission_phase": "on_station"}])
    provider = MissionProvider()
    snapshot = provider.get_snapshot()
    row = snapshot["mission_phase_status"][0]
    assert row["mission_id"] == "m-2"
    assert row["status"] == "paused"
    assert row["phase"] == "on_station"
