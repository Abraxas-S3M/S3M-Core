"""Tests for readiness adapter fatigue-panel integration."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.api import readiness_routes
from src.api.gui_bridge.adapters.readiness_adapter import ReadinessAdapter


def _build_member(
    *,
    status: str,
    training_score: float,
    sleep_hours: float,
    now: datetime,
) -> SimpleNamespace:
    sleep_end = now - timedelta(hours=1)
    sleep_start = sleep_end - timedelta(hours=sleep_hours)
    return SimpleNamespace(
        status=SimpleNamespace(value=status),
        training_score=training_score,
        sleep_history=[(sleep_start, sleep_end)],
    )


def test_get_certifications_includes_shift_rotation_fatigue_row(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    members = [
        _build_member(status="ACTIVE_DUTY", training_score=92.0, sleep_hours=8.0, now=now),
        _build_member(status="DEPLOYED", training_score=65.0, sleep_hours=4.5, now=now),
        _build_member(status="TRAINING", training_score=75.0, sleep_hours=6.0, now=now),
    ]

    fake_registry = SimpleNamespace(get_members=lambda: members)
    fake_readiness = SimpleNamespace(personnel_registry=fake_registry)
    monkeypatch.setattr(readiness_routes, "_readiness", fake_readiness, raising=False)

    adapter = ReadinessAdapter()
    rows = adapter._get_certifications()
    fatigue_row = next((row for row in rows if row.certType == "SHIFT_ROTATION_FATIGUE"), None)

    assert fatigue_row is not None
    assert fatigue_row.total == len(members)
    assert fatigue_row.current + fatigue_row.expiringSoon + fatigue_row.expired == len(members)
