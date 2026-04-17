"""Unit tests for tactical mission uplift scoring."""

from __future__ import annotations

from s3m_core.evaluation.uplift_scorer import UpliftReport, UpliftScorer


def test_score_mission_generates_autonomous_uplift_report() -> None:
    scorer = UpliftScorer()
    mission = {
        "mission_id": "convoy_alpha",
        "model_version": "v2.1",
        "total_tasks": 10,
        "tasks_completed_autonomously": 8,
        "tasks_requiring_human": 2,
        "human_time_minutes": 120.0,
        "s3m_time_minutes": 78.0,
        "human_quality": 0.64,
        "s3m_quality": 0.88,
        "novel_solutions": 2,
        "timestamp": "2026-04-17T10:00:00+00:00",
    }

    report = scorer.score_mission(mission)

    assert isinstance(report, UpliftReport)
    assert 0.0 <= report.score <= 4.0
    assert report.category in {
        "no improvement",
        "basic assistance",
        "expert-level support",
        "autonomous execution",
        "strategic superiority",
    }
    assert report.time_saved_estimate == 42.0
    assert report.quality_delta == 0.24
    assert report.tasks_completed_autonomously == 8
    assert report.tasks_requiring_human == 2
    assert report.novel_solutions == 2


def test_compare_versions_detects_regressions() -> None:
    scorer = UpliftScorer()
    baseline = [
        UpliftReport(3.2, "autonomous execution", 40.0, 0.20, 8, 2, 1),
        UpliftReport(3.0, "autonomous execution", 35.0, 0.16, 7, 3, 1),
    ]
    candidate = [
        UpliftReport(2.2, "expert-level support", 20.0, 0.08, 5, 5, 0),
        UpliftReport(2.1, "expert-level support", 18.0, 0.05, 4, 6, 0),
    ]

    report = scorer.compare_versions(baseline, candidate)

    assert "score" in report.regressed
    assert "time_saved_estimate" in report.regressed
    assert "quality_delta" in report.regressed
    assert "tasks_requiring_human" in report.regressed
    assert report.overall_delta < 0.0


def test_generate_dashboard_data_groups_by_category_and_version() -> None:
    scorer = UpliftScorer()
    scorer.score_mission(
        {
            "mission_id": "isr_1",
            "model_version": "v1",
            "total_tasks": 6,
            "tasks_completed_autonomously": 3,
            "tasks_requiring_human": 3,
            "human_time_minutes": 70.0,
            "s3m_time_minutes": 60.0,
            "human_quality": 0.5,
            "s3m_quality": 0.58,
            "novel_solutions": 0,
        }
    )
    scorer.score_mission(
        {
            "mission_id": "isr_2",
            "model_version": "v2",
            "total_tasks": 6,
            "tasks_completed_autonomously": 5,
            "tasks_requiring_human": 1,
            "human_time_minutes": 70.0,
            "s3m_time_minutes": 45.0,
            "human_quality": 0.5,
            "s3m_quality": 0.8,
            "novel_solutions": 2,
        }
    )

    data = scorer.generate_dashboard_data()

    assert len(data["uplift_over_time"]) == 2
    assert "by_category" in data
    assert "by_model_version" in data
    assert set(data["by_model_version"]) == {"v1", "v2"}
