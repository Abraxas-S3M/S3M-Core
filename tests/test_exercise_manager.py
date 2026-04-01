"""Tests for Phase 16 exercise manager lifecycle and integration."""

from __future__ import annotations

from services.interop.exercise_manager import ExerciseManager


def _exercise(manager: ExerciseManager) -> int:
    session = manager.create_exercise(
        name="GCC Joint Shield 2026",
        description="Lifecycle validation",
        nations=[
            {"country_code": 178, "name": "Saudi Arabia", "callsign": "FALCON"},
            {"country_code": 223, "name": "United Arab Emirates", "callsign": "HAWK"},
        ],
    )
    return session.exercise_id


def test_create_exercise_returns_session():
    manager = ExerciseManager()
    exercise_id = _exercise(manager)
    session = manager.get_exercise(exercise_id)
    assert session is not None
    assert session.exercise_name == "GCC Joint Shield 2026"


def test_start_exercise_sets_active():
    manager = ExerciseManager()
    exercise_id = _exercise(manager)
    assert manager.start_exercise(exercise_id) is True
    assert manager.get_exercise(exercise_id).status == "active"


def test_pause_exercise_sets_paused():
    manager = ExerciseManager()
    exercise_id = _exercise(manager)
    manager.start_exercise(exercise_id)
    manager.pause_exercise(exercise_id)
    assert manager.get_exercise(exercise_id).status == "paused"


def test_end_exercise_sets_completed():
    manager = ExerciseManager()
    exercise_id = _exercise(manager)
    manager.start_exercise(exercise_id)
    summary = manager.end_exercise(exercise_id)
    session = manager.get_exercise(exercise_id)
    assert session.status == "completed"
    assert session.end_time is not None
    assert summary["status"] == "completed"


def test_inject_scenario_populates_entities():
    manager = ExerciseManager()
    exercise_id = _exercise(manager)
    scenario = {
        "scenario_id": "scn-1",
        "name": "Inject",
        "forces": [
            {
                "force_id": "f1",
                "affiliation": "friendly",
                "units": [
                    {
                        "unit_id": "u1",
                        "name": "Unit 1",
                        "designation": "Alpha",
                        "position": (24.7, 46.7),
                    }
                ],
            }
        ],
        "environment": {"terrain": "desert"},
    }
    manager.inject_scenario(exercise_id, scenario)
    assert manager.get_exercise(exercise_id).events_count >= 1


def test_get_active_exercises_filters():
    manager = ExerciseManager()
    ex1 = _exercise(manager)
    ex2 = _exercise(manager)
    manager.start_exercise(ex1)
    active_ids = {row.exercise_id for row in manager.get_active_exercises()}
    assert ex1 in active_ids
    assert ex2 not in active_ids
