"""Unit tests for long-horizon mission memory."""

from __future__ import annotations

from s3m_core.memory.mission_memory import EmotionProfile, MissionMemory, MissionStep


def test_mission_memory_create_save_context_and_lessons(tmp_path) -> None:
    memory = MissionMemory(storage_path=str(tmp_path))
    mission = memory.create_mission(
        mission_id="mission-alpha",
        objective="Secure contested relay node",
        constraints=["Avoid civilian infrastructure", "Maintain emissions discipline"],
    )
    assert mission.mission_id == "mission-alpha"

    step = MissionStep(
        step_id="step-001",
        description="Scan relay perimeter for EW threats",
        action_taken="Executed passive RF scan and cross-checked threat signatures",
        result="Confirmed low-noise corridor and marked safe ingress route",
        success=True,
        duration_seconds=42.5,
        tokens_used=1200,
        sae_alerts=[],
        emotion_profile=EmotionProfile(stress=0.3, confidence=0.8, focus=0.9),
    )
    memory.save_step("mission-alpha", step)
    memory.add_lesson("mission-alpha", "Stage fallback communication links before EW-heavy maneuvers.")

    context = memory.get_mission_context("mission-alpha", max_tokens=200)
    assert "Mission ID: mission-alpha" in context
    assert "STEP step-001" in context

    relevant = memory.get_relevant_lessons("Need resilient relay communications under EW pressure", top_k=3)
    assert relevant
    assert "fallback communication links" in relevant[0]


def test_mission_memory_recursive_summary_respects_budget(tmp_path) -> None:
    memory = MissionMemory(storage_path=str(tmp_path))
    memory.create_mission("mission-bravo", "Track mobile launcher", ["Avoid blue-force fratricide"])

    for index in range(8):
        memory.save_step(
            "mission-bravo",
            MissionStep(
                step_id=f"step-{index}",
                description="Correlate ISR feeds and update intercept geometry",
                action_taken="Fused tracks and recalculated route options for deconflicted intercept",
                result="Route update generated with confidence bounds and fallback vectors",
                success=True,
                duration_seconds=30.0 + index,
                tokens_used=900 + index,
                sae_alerts=[],
                emotion_profile=EmotionProfile(stress=0.2, confidence=0.7, focus=0.85),
            ),
        )

    summary = memory.get_mission_context("mission-bravo", max_tokens=60)
    assert len(summary.split()) <= 60
