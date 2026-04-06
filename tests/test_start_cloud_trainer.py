"""Unit tests for cloud trainer startup script."""

from __future__ import annotations

import signal

from scripts import start_cloud_trainer


def test_select_tracks_returns_all_when_env_empty() -> None:
    tracks = start_cloud_trainer._select_tracks("")
    assert [track.value for track in tracks]
    assert len(tracks) >= 3


def test_handle_signal_requests_shutdown_and_stops_services(monkeypatch) -> None:
    class _FakeService:
        def __init__(self) -> None:
            self.stop_calls = 0

        def stop(self) -> None:
            self.stop_calls += 1

    start_cloud_trainer._shutdown = False
    svc = _FakeService()
    start_cloud_trainer._services = [svc]

    start_cloud_trainer._handle_signal(signal.SIGTERM, None)

    assert start_cloud_trainer._shutdown is True
    assert svc.stop_calls == 1


def test_main_single_track_invokes_service_start(monkeypatch) -> None:
    calls: dict[str, int] = {"start": 0}

    class _FakeService:
        def __init__(self, track, paths) -> None:
            _ = (track, paths)

        def start(self) -> None:
            calls["start"] += 1

        def stop(self) -> None:
            return None

    monkeypatch.setattr(start_cloud_trainer, "TrainerService", _FakeService)
    monkeypatch.setenv("S3M_TRAINING_TRACK", "nato")
    start_cloud_trainer._services = []
    start_cloud_trainer._shutdown = False

    rc = start_cloud_trainer.main()
    assert rc == 0
    assert calls["start"] == 1


def test_main_round_robin_runs_until_shutdown(monkeypatch) -> None:
    calls = {"cycles": 0}

    class _FakeService:
        def __init__(self, track, paths) -> None:
            _ = (track, paths)

        def run_cycle_once(self) -> None:
            calls["cycles"] += 1
            if calls["cycles"] >= 3:
                start_cloud_trainer._shutdown = True

        def stop(self) -> None:
            return None

        def get_status(self) -> dict[str, str]:
            return {"track": "fake"}

    monkeypatch.setattr(start_cloud_trainer, "TrainerService", _FakeService)
    monkeypatch.setenv("S3M_TRAINING_TRACK", "")
    start_cloud_trainer._services = []
    start_cloud_trainer._shutdown = False

    rc = start_cloud_trainer.main()
    assert rc == 0
    assert calls["cycles"] >= 3
