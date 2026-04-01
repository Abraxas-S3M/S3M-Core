from __future__ import annotations

from services.interop.coalition_dashboard import CoalitionDashboardProvider
from services.interop.exercise_manager import ExerciseManager


def _create_started_exercise(manager: ExerciseManager) -> int:
    session = manager.create_exercise(
        name="Coalition Test",
        description="Dashboard test exercise",
        nations=[
            {"country_code": 178, "name": "Saudi Arabia", "callsign": "FALCON"},
            {"country_code": 223, "name": "United Arab Emirates", "callsign": "HAWK"},
        ],
    )
    manager.start_exercise(session.exercise_id)
    return session.exercise_id


def test_get_exercise_overview_returns_expected_keys():
    manager = ExerciseManager()
    exercise_id = _create_started_exercise(manager)
    dashboard = CoalitionDashboardProvider(manager)
    overview = dashboard.get_exercise_overview(str(exercise_id))
    expected = {
        "exercise",
        "nations",
        "entities",
        "events",
        "c2sim_messages",
        "dis_pdus",
        "timeline",
    }
    assert expected.issubset(set(overview.keys()))


def test_get_orbat_view_returns_hierarchical_structure():
    manager = ExerciseManager()
    force = manager.orbat_manager.create_saudi_template()
    dashboard = CoalitionDashboardProvider(manager)
    view = dashboard.get_orbat_view(force.force_id)
    assert "force" in view
    assert "hierarchy" in view
    assert isinstance(view["hierarchy"], list)


def test_get_coalition_cop_returns_merged_entity_data():
    manager = ExerciseManager()
    _create_started_exercise(manager)
    dashboard = CoalitionDashboardProvider(manager)
    cop = dashboard.get_coalition_cop()
    assert "entities" in cop
    assert "reports" in cop
    assert "exercise_count" in cop


def test_get_interop_metrics_returns_dis_and_c2sim_stats():
    manager = ExerciseManager()
    _create_started_exercise(manager)
    dashboard = CoalitionDashboardProvider(manager)
    metrics = dashboard.get_interop_metrics()
    assert "dis" in metrics
    assert "c2sim" in metrics
    assert "latency_ms" in metrics
