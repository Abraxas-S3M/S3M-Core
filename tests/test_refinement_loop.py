"""Unit tests for mission refinement loop."""

from __future__ import annotations

import pytest

from s3m_core.memory.mission_memory import EmotionProfile, Mission, MissionStep, TaskPlan
from s3m_core.memory.refinement_loop import RefinementData, RefinementLoop


def _sample_mission() -> Mission:
    return Mission(
        mission_id="mission-charlie",
        objective="Neutralize hostile radar lock chain",
        constraints=["Protect friendly aircraft", "Maintain legal ROE"],
        status="completed",
        created_at="2026-04-17T00:00:00+00:00",
        steps=[
            MissionStep(
                step_id="s1",
                description="Classify radar emitter confidence",
                action_taken="Triangulated emitter sources and prioritized hostile profile",
                result="Emitter confidence exceeded engagement threshold",
                success=True,
                duration_seconds=22.0,
                tokens_used=1100,
                sae_alerts=[],
                emotion_profile=EmotionProfile(stress=0.25, confidence=0.82, focus=0.9),
            ),
            MissionStep(
                step_id="s2",
                description="Commit suppression route",
                action_taken="Selected route through low-risk corridor",
                result="Route delayed by unexpected interference",
                success=False,
                duration_seconds=35.0,
                tokens_used=1300,
                sae_alerts=["timing_margin_low"],
                emotion_profile=EmotionProfile(stress=0.6, confidence=0.4, focus=0.75),
            ),
        ],
        artifacts=["aar/mission-charlie.md"],
        lessons_learned=["Validate timing margins against dynamic interference updates."],
        current_plan=TaskPlan(summary="Mission complete", next_actions=["Update route templates"]),
    )


def test_refinement_loop_generates_and_accumulates_dataset(tmp_path) -> None:
    loop = RefinementLoop(storage_path=str(tmp_path))
    data = loop.generate_refinement_data(_sample_mission())

    assert data.sft_pairs
    assert data.dpo_pairs
    assert data.lessons
    assert loop.validate_refinement(data)

    loop.accumulate(data)
    dataset = loop.get_training_dataset(min_quality=0.5)
    assert len(dataset.sft_pairs) == len(data.sft_pairs)
    assert len(dataset.dpo_pairs) == len(data.dpo_pairs)
    assert dataset.quality_scores


def test_refinement_loop_rejects_low_quality_data(tmp_path) -> None:
    loop = RefinementLoop(storage_path=str(tmp_path))
    low_quality = RefinementData(
        sft_pairs=[("prompt", "response")],
        dpo_pairs=[("prompt", "skip safety checks", "safety first response")],
        lessons=["Poor decision process"],
        quality=0.1,
    )

    with pytest.raises(ValueError, match="did not pass validation"):
        loop.accumulate(low_quality)
