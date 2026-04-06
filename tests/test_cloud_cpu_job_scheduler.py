"""Unit tests for cloud CPU duty-cycle scheduler."""

from __future__ import annotations

from src.training.cloud_cpu import job_scheduler


class _Clock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


def test_scheduler_transitions_between_train_and_sleep(monkeypatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(job_scheduler.time, "monotonic", clock.monotonic)

    scheduler = job_scheduler.JobScheduler(train_seconds=10.0, sleep_seconds=5.0)
    assert scheduler.should_train() is True
    assert scheduler.should_sleep() is False

    clock.now += 11.0
    assert scheduler.should_sleep() is True
    assert scheduler.should_train() is False

    clock.now += 6.0
    assert scheduler.should_train() is True
    assert scheduler.should_sleep() is False


def test_scheduler_applies_pause_and_recovers_default_cycle(monkeypatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(job_scheduler.time, "monotonic", clock.monotonic)

    scheduler = job_scheduler.JobScheduler(train_seconds=20.0, sleep_seconds=4.0)
    scheduler.apply_throttle_recommendation("pause")
    assert scheduler.should_sleep() is True

    scheduler.apply_throttle_recommendation("none")
    scheduler.reset_cycle()
    assert scheduler.should_train() is True
