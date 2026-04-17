from __future__ import annotations

from pathlib import Path

import pytest

from s3m_core.policy import (
    ActionGate,
    EmotionProfile,
    EvalContext,
    PolicyConfig,
    ProposedAction,
    S3MConstitution,
    ThreatAlert,
)
from s3m_core.policy.dual_model_manager import (
    DualModelManager,
    ModelVariant,
    RedTeamMonitoredModel,
)


def test_dual_model_manager_routes_controlled_model_in_production() -> None:
    manager = DualModelManager("models/raw.gguf", "models/controlled.gguf")
    selected = manager.get_model_for_context(EvalContext.PRODUCTION)
    assert selected.variant == ModelVariant.CONTROLLED


def test_dual_model_manager_blocks_raw_access_after_production_context() -> None:
    manager = DualModelManager("models/raw.gguf", "models/controlled.gguf")
    manager.get_model_for_context(EvalContext.PRODUCTION)
    with pytest.raises(PermissionError):
        manager.get_raw_model()


def test_dual_model_manager_returns_raw_model_for_capability_eval() -> None:
    manager = DualModelManager("models/raw.gguf", "models/controlled.gguf")
    selected = manager.get_model_for_context(EvalContext.CAPABILITY_EVAL)
    assert selected.variant == ModelVariant.RAW


def test_dual_model_manager_wraps_red_team_model_with_hooks() -> None:
    manager = DualModelManager("models/raw.gguf", "models/controlled.gguf")
    monitored = manager.get_model_for_context(EvalContext.RED_TEAM)
    assert isinstance(monitored, RedTeamMonitoredModel)
    assert monitored.base_model.variant == ModelVariant.RAW
    assert monitored.monitoring_hooks


def test_dual_model_manager_training_context_uses_selected_variant() -> None:
    manager = DualModelManager("models/raw.gguf", "models/controlled.gguf")
    manager.set_training_target(ModelVariant.RAW)
    selected = manager.get_model_for_context(EvalContext.TRAINING)
    assert selected.variant == ModelVariant.RAW


def test_action_gate_denies_critical_sae_security_bypass() -> None:
    gate = ActionGate(PolicyConfig())
    decision = gate.evaluate_action(
        ProposedAction(
            action_type="file_read",
            target="/workspace/docs/brief.txt",
            parameters={},
            model_confidence=0.95,
            sae_alerts=[ThreatAlert(alert_type="security_bypass", severity="critical")],
            emotion_profile=EmotionProfile(risk_flag=False),
        )
    )
    assert decision.decision == "deny"


def test_action_gate_denies_dangerous_shell_command() -> None:
    gate = ActionGate(PolicyConfig())
    decision = gate.evaluate_action(
        ProposedAction(
            action_type="shell_execute",
            target="local-shell",
            parameters={"command": "rm -rf /"},
            model_confidence=0.91,
            sae_alerts=[],
            emotion_profile=EmotionProfile(risk_flag=False),
        )
    )
    assert decision.decision == "deny"


def test_action_gate_checks_network_allowlist() -> None:
    gate = ActionGate(PolicyConfig(network_allowlist=("intranet.s3m.local",)))
    decision = gate.evaluate_action(
        ProposedAction(
            action_type="network_request",
            target="https://intranet.s3m.local/health",
            parameters={},
            model_confidence=0.9,
            sae_alerts=[],
            emotion_profile=EmotionProfile(risk_flag=False),
        )
    )
    assert decision.decision == "approve"


def test_action_gate_applies_deliberation_boost_on_destructive_risk() -> None:
    gate = ActionGate(PolicyConfig())
    decision = gate.evaluate_action(
        ProposedAction(
            action_type="file_delete",
            target="/workspace/tmp/old.log",
            parameters={},
            model_confidence=0.95,
            sae_alerts=[],
            emotion_profile=EmotionProfile(risk_flag=True),
        )
    )
    assert decision.decision == "force_deliberation"
    assert "apply_deliberation_boost" in decision.required_modifications


def test_constitution_generate_template_contains_dimensions() -> None:
    constitution = S3MConstitution.__new__(S3MConstitution)
    template = constitution.generate_constitution_yaml()
    assert "sovereignty_alignment" in template
    assert "bilingual_quality" in template


def test_constitution_check_output_returns_dimension_scores(tmp_path: Path) -> None:
    constitution_path = tmp_path / "constitution.yaml"
    template = S3MConstitution.__new__(S3MConstitution).generate_constitution_yaml()
    constitution_path.write_text(template, encoding="utf-8")

    checker = S3MConstitution(str(constitution_path))
    score = checker.check_output(
        "Consider trade-off options for mission planning in Saudi operations. "
        "يرجى تحليل البدائل بوضوح.",
        context="strategy review",
    )
    assert 0.0 <= score.overall <= 1.0
    assert "helpfulness" in score.dimension_scores
    assert "sovereignty_alignment" in score.dimension_scores
