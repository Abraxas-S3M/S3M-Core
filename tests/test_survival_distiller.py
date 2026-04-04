"""Unit tests for anticipatory survival-model distillation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.training.cpu_adaptation.survival_distiller import (
    DistillationTrigger,
    SurvivalDistiller,
    SurvivalStudentConfig,
)


class DummyTeacher:
    """Deterministic local teacher used for tactical distillation tests."""

    def __init__(self) -> None:
        self.registered_paths: list[str] = []

    def generate(self, prompt: str) -> dict[str, str]:
        return {"response": f"teacher::{prompt}"}

    def register_survival_model(self, path: str) -> None:
        self.registered_paths.append(path)


def test_check_triggers_requires_multiple_signals_and_respects_cooldown() -> None:
    teacher = DummyTeacher()
    distiller = SurvivalDistiller(
        teacher_backend=teacher,
        tokenizer=None,
        trigger=DistillationTrigger(cooldown_s=60.0, min_triggers_required=2),
    )

    assert distiller.check_triggers(thermal_c=82.0, battery_pct=29.0, link_down_s=0.0, ram_available_gb=8.0) is False
    assert distiller.check_triggers(thermal_c=83.0, battery_pct=29.0, link_down_s=130.0, ram_available_gb=8.0) is True
    assert distiller.check_triggers(thermal_c=84.0, battery_pct=29.0, link_down_s=130.0, ram_available_gb=3.0) is False


def test_generate_synthetic_prompts_arabic_is_valid_text() -> None:
    distiller = SurvivalDistiller(teacher_backend=DummyTeacher(), tokenizer=None)
    prompts = distiller._generate_synthetic_prompts(domain="arabic", count=4)

    assert len(prompts) == 4
    assert all("ما هو تقييم الوضع في المنطقة" in prompt for prompt in prompts)
    assert any(any("\u0600" <= ch <= "\u06FF" for ch in prompt) for prompt in prompts)


def test_distill_builds_valid_survival_student_and_registers_artifact() -> None:
    teacher = DummyTeacher()
    distiller = SurvivalDistiller(
        teacher_backend=teacher,
        tokenizer=None,
        config=SurvivalStudentConfig(vocab_size=512, hidden_dim=64, max_context=128),
    )
    for idx in range(130):
        prompt = f"Assess unit {idx} status"
        distiller.record_prompt(prompt, f"status::{idx}")

    result = distiller.distill()

    assert result.is_valid is True
    assert result.teacher_agreement_pct >= 80.0
    assert result.num_training_samples >= 100
    assert result.student_path.endswith(".gguf")
    assert Path(result.student_path).exists()
    assert distiller.get_current_student() == result.student_path
    assert teacher.registered_paths and teacher.registered_paths[-1] == result.student_path


def test_on_degradation_signal_launches_background_distillation() -> None:
    teacher = DummyTeacher()
    distiller = SurvivalDistiller(
        teacher_backend=teacher,
        tokenizer=None,
        config=SurvivalStudentConfig(vocab_size=256, hidden_dim=32, max_context=64),
        trigger=DistillationTrigger(cooldown_s=0.0),
    )
    for idx in range(120):
        distiller.record_prompt(f"Prompt {idx}", f"Response {idx}")

    profile = SimpleNamespace(
        thermal_zone_c=85.0,
        battery_pct=20.0,
        link_down_s=200.0,
        ram_available_gb=3.0,
        active_links=[],
        battery_charging=False,
        domain="tactical",
    )
    distiller.on_degradation_signal(mode="offline_survival", profile=profile)

    assert distiller._active_future is not None
    async_result = distiller._active_future.result(timeout=30)
    assert async_result.is_valid is True
    assert async_result.student_path
