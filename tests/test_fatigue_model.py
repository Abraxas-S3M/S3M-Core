"""Unit tests for Dawson-Reid fatigue scoring."""

from datetime import datetime, timedelta, timezone

import pytest

from src.readiness.fatigue_model import DawsonReidFatigueModel


def test_compute_fatigue_score_stays_in_expected_range() -> None:
    model = DawsonReidFatigueModel()
    current_time = datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc)
    sleep_history = [
        (
            current_time - timedelta(hours=9),
            current_time - timedelta(hours=2),
        )
    ]
    score = model.compute_fatigue_score(sleep_history=sleep_history, current_time=current_time)
    assert 0.0 <= score <= 100.0


def test_recent_sleep_scores_higher_than_long_wake() -> None:
    model = DawsonReidFatigueModel()
    current_time = datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc)

    recently_rested = [
        (
            current_time - timedelta(hours=9),
            current_time - timedelta(hours=2),
        )
    ]
    stale_sleep = [
        (
            current_time - timedelta(hours=34),
            current_time - timedelta(hours=27),
        )
    ]

    rested_score = model.compute_fatigue_score(recently_rested, current_time)
    fatigued_score = model.compute_fatigue_score(stale_sleep, current_time)
    assert rested_score > fatigued_score


def test_circadian_peak_scores_higher_than_trough() -> None:
    model = DawsonReidFatigueModel()
    peak_time = datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc)
    trough_time = datetime(2026, 4, 8, 3, 0, tzinfo=timezone.utc)

    sleep_history = [
        (
            peak_time - timedelta(hours=10),
            peak_time - timedelta(hours=3),
        )
    ]

    peak_score = model.compute_fatigue_score(sleep_history=sleep_history, current_time=peak_time)
    trough_score = model.compute_fatigue_score(sleep_history=sleep_history, current_time=trough_time)
    assert peak_score > trough_score


def test_compute_fatigue_score_rejects_naive_datetimes() -> None:
    model = DawsonReidFatigueModel()
    with pytest.raises(ValueError):
        model.compute_fatigue_score(
            sleep_history=[],
            current_time=datetime(2026, 4, 8, 15, 0),
        )
