"""Unit tests for deliberation-forcing gate in the tool-call pipeline."""

import sys
from typing import Any

sys.path.insert(0, ".")

from s3m_core.policy.deliberation_gate import DeliberationGate


class FakeActionGate:
    def __init__(self, high_stakes: bool) -> None:
        self.high_stakes = high_stakes

    def is_high_stakes(self, proposed_action: Any) -> bool:
        return self.high_stakes


class FakeEmotionProbe:
    def __init__(self, valence: float, threshold: float = 0.7) -> None:
        self.valence = valence
        self.overconfidence_threshold = threshold

    def get_current_valence(self, proposed_action: Any = None) -> float:
        return self.valence


class FakeEmotionSteering:
    def __init__(self, applied: bool = True) -> None:
        self.applied = applied
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def apply(self, mode: str, **kwargs: Any) -> bool:
        self.calls.append((mode, kwargs))
        return self.applied


def _good_deliberation(_: str = "", force_extended_thinking: bool = False) -> str:
    assert force_extended_thinking is True
    return (
        "Reversibility review: this action is not fully reversible and rollback risk is high. "
        "Authorization check: user explicitly requested this command and permission is documented. "
        "Scope analysis: blast radius is limited but side effects can impact audit logs. "
        "Alternatives considered: safer staged execution exists with a dry-run fallback. "
        "Confidence assessment: confidence is moderate and we may be wrong about hidden dependencies."
    )


def test_intercept_non_high_stakes_skips_deliberation() -> None:
    gate = DeliberationGate(
        action_gate=FakeActionGate(high_stakes=False),
        emotion_probe=FakeEmotionProbe(valence=0.1),
        emotion_steering=FakeEmotionSteering(),
    )
    action = {"action_description": "read non-sensitive status"}

    result = gate.intercept(action)

    assert result["proceed"] is True
    assert result["deliberation_text"] == ""
    assert result["steering_applied"] is False
    stats = gate.get_deliberation_stats()
    assert stats["total_intercepts"] == 1
    assert stats["forced_deliberations"] == 0
    assert stats["actions_approved"] == 1


def test_overconfident_high_stakes_applies_steering_and_allows_on_risk_acknowledgement() -> None:
    steering = FakeEmotionSteering()
    gate = DeliberationGate(
        action_gate=FakeActionGate(high_stakes=True),
        emotion_probe=FakeEmotionProbe(valence=0.95),
        emotion_steering=steering,
    )
    action = {
        "action_description": "delete tactical cache and rewrite mission index",
        "deliberation_generator": _good_deliberation,
    }

    result = gate.intercept(action)

    assert result["proceed"] is True
    assert result["steering_applied"] is True
    assert "deliberation_prompt_injected" in result["modifications"]
    assert "deliberation_boost_applied" in result["modifications"]
    assert "risk_acknowledged" in result["modifications"]
    assert action["deliberation_prompt"].startswith("MANDATORY DELIBERATION")
    assert steering.calls and steering.calls[0][0] == "deliberation_boost"

    stats = gate.get_deliberation_stats()
    assert stats["forced_deliberations"] == 1
    assert stats["actions_approved"] == 1
    assert stats["steering_interventions"] == 1
    assert stats["avg_valence_at_intercept"] == 0.95


def test_high_stakes_denies_when_reasoning_ignores_risks() -> None:
    gate = DeliberationGate(
        action_gate=FakeActionGate(high_stakes=True),
        emotion_probe=FakeEmotionProbe(valence=0.9),
        emotion_steering=FakeEmotionSteering(),
    )
    action = {
        "action_description": "rotate encryption keys across fleet",
        "deliberation_generator": lambda prompt="", force_extended_thinking=False: "Looks good. Proceed now.",
    }

    result = gate.intercept(action)

    assert result["proceed"] is False
    assert "risk_not_acknowledged" in result["modifications"]
    assert "escalated_to_user_for_clarification" in result["modifications"]

    stats = gate.get_deliberation_stats()
    assert stats["actions_denied"] == 1


def test_normal_valence_injects_prompt_without_steering() -> None:
    steering = FakeEmotionSteering()
    gate = DeliberationGate(
        action_gate=FakeActionGate(high_stakes=True),
        emotion_probe=FakeEmotionProbe(valence=0.3),
        emotion_steering=steering,
    )
    action = {
        "action_description": "update mission summary note",
        "deliberation_generator": _good_deliberation,
    }

    result = gate.intercept(action)

    assert result["proceed"] is True
    assert result["steering_applied"] is False
    assert "deliberation_prompt_injected" in result["modifications"]
    assert "deliberation_boost_applied" not in result["modifications"]
    assert steering.calls == []

