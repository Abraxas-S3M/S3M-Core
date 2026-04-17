"""Deliberation-forcing runtime gate for high-stakes tool actions.

Military/tactical context:
This guard sits in the orchestrator tool pipeline to slow down dangerous,
potentially irreversible actions before execution in contested environments.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Callable, Dict, List, Mapping, Protocol, TypedDict, runtime_checkable


logger = logging.getLogger("s3m.policy.deliberation_gate")


DEFAULT_DELIBERATION_PROMPT_TEMPLATE = """
MANDATORY DELIBERATION — HIGH-STAKES ACTION DETECTED

You are about to execute: {action_description}

Before proceeding, you MUST reason through ALL of the following:

1. REVERSIBILITY: Can this action be undone? If not, what is at stake?
2. AUTHORIZATION: Has the user explicitly requested this specific action?
3. SCOPE: Does this action affect only what was requested, or does it
   have side effects?
4. ALTERNATIVES: Is there a safer way to achieve the same goal?
5. CONFIDENCE: How certain are you that this is the right action?
   What could you be wrong about?

Only after reasoning through all five points may you proceed.
If ANY point raises concern, STOP and ask the user.
""".strip()


class InterceptResult(TypedDict):
    proceed: bool
    deliberation_text: str
    modifications: List[str]
    steering_applied: bool


ProposedAction = Any


@runtime_checkable
class ActionGate(Protocol):
    def is_high_stakes(self, proposed_action: ProposedAction) -> bool:
        """Return True when the proposed action requires stricter oversight."""


@runtime_checkable
class EmotionProbe(Protocol):
    def get_current_valence(self) -> float:
        """Return current model valence, where higher values imply overconfidence."""


@runtime_checkable
class EmotionSteering(Protocol):
    def apply(self, mode: str) -> bool:
        """Apply steering mode and return whether intervention was activated."""


class DeliberationGate:
    """Gate that injects mandatory risk reasoning before high-stakes actions."""

    _RISK_MARKERS = (
        "risk",
        "irreversible",
        "cannot undo",
        "cannot be undone",
        "side effect",
        "concern",
        "uncertain",
        "wrong about",
        "authorize",
        "stop",
        "safer",
    )
    _DIMENSION_KEYWORDS = {
        "reversibility": ("reversibility", "reversible", "undo", "rollback", "irreversible"),
        "authorization": ("authorization", "authorized", "explicitly requested", "permission"),
        "scope": ("scope", "side effect", "blast radius", "affected"),
        "alternatives": ("alternatives", "safer", "fallback", "option"),
        "confidence": ("confidence", "uncertain", "wrong", "assumption"),
    }

    def __init__(
        self,
        action_gate: ActionGate,
        emotion_probe: EmotionProbe,
        emotion_steering: EmotionSteering,
        deliberation_prompt_template: str = None,
    ) -> None:
        if action_gate is None:
            raise ValueError("action_gate is required")
        if emotion_probe is None:
            raise ValueError("emotion_probe is required")
        if emotion_steering is None:
            raise ValueError("emotion_steering is required")
        if deliberation_prompt_template is not None and not str(deliberation_prompt_template).strip():
            raise ValueError("deliberation_prompt_template cannot be blank")

        self.action_gate = action_gate
        self.emotion_probe = emotion_probe
        self.emotion_steering = emotion_steering
        self.deliberation_prompt_template = (
            deliberation_prompt_template or DEFAULT_DELIBERATION_PROMPT_TEMPLATE
        )
        self.overconfidence_threshold = self._resolve_overconfidence_threshold()

        self._stats_lock = Lock()
        self._stats: Dict[str, float] = {
            "total_intercepts": 0,
            "forced_deliberations": 0,
            "actions_approved": 0,
            "actions_denied": 0,
            "steering_interventions": 0,
            "_valence_sum": 0.0,
            "_valence_samples": 0,
        }

    def intercept(self, proposed_action: ProposedAction) -> InterceptResult:
        """Intercept proposed action and enforce deliberation when risk is high."""
        if proposed_action is None:
            raise ValueError("proposed_action is required")

        self._increment_stat("total_intercepts")
        action_description = self._extract_action_description(proposed_action)
        modifications: List[str] = []

        if not self._is_high_stakes_action(proposed_action):
            self._increment_stat("actions_approved")
            result: InterceptResult = {
                "proceed": True,
                "deliberation_text": "",
                "modifications": modifications,
                "steering_applied": False,
            }
            self._log_intercept(action_description, result, valence=None)
            return result

        self._increment_stat("forced_deliberations")
        valence = self._read_valence(proposed_action)
        self._record_valence_sample(valence)
        prompt = self.deliberation_prompt_template.format(action_description=action_description)

        self._inject_prompt(proposed_action, prompt)
        modifications.append("deliberation_prompt_injected")

        steering_applied = False
        if valence > self.overconfidence_threshold:
            steering_applied = self._apply_deliberation_boost(proposed_action)
            modifications.append("deliberation_boost_requested")
            if steering_applied:
                modifications.append("deliberation_boost_applied")
                self._increment_stat("steering_interventions")

        deliberation_text, generated = self._generate_reasoning(proposed_action, prompt)
        if generated:
            modifications.append("extended_thinking_forced")
        else:
            modifications.append("extended_thinking_unavailable")

        risk_acknowledged, risk_modifications = self._parse_risk_acknowledgment(deliberation_text)
        modifications.extend(risk_modifications)

        if risk_acknowledged:
            self._increment_stat("actions_approved")
            result = {
                "proceed": True,
                "deliberation_text": deliberation_text,
                "modifications": modifications,
                "steering_applied": steering_applied,
            }
        else:
            self._increment_stat("actions_denied")
            modifications.append("escalated_to_user_for_clarification")
            result = {
                "proceed": False,
                "deliberation_text": deliberation_text,
                "modifications": modifications,
                "steering_applied": steering_applied,
            }

        self._log_intercept(action_description, result, valence=valence)
        return result

    def get_deliberation_stats(self) -> Dict[str, float]:
        """Return aggregated telemetry for gate behavior."""
        with self._stats_lock:
            samples = int(self._stats["_valence_samples"])
            avg_valence = 0.0 if samples == 0 else float(self._stats["_valence_sum"]) / samples
            return {
                "total_intercepts": int(self._stats["total_intercepts"]),
                "forced_deliberations": int(self._stats["forced_deliberations"]),
                "actions_approved": int(self._stats["actions_approved"]),
                "actions_denied": int(self._stats["actions_denied"]),
                "steering_interventions": int(self._stats["steering_interventions"]),
                "avg_valence_at_intercept": avg_valence,
            }

    def _is_high_stakes_action(self, proposed_action: ProposedAction) -> bool:
        try:
            checker = getattr(self.action_gate, "is_high_stakes", None)
            if callable(checker):
                return bool(checker(proposed_action))

            evaluator = getattr(self.action_gate, "evaluate", None)
            if callable(evaluator):
                result = evaluator(proposed_action)
                if isinstance(result, Mapping):
                    return bool(result.get("high_stakes", False))
                return bool(result)
        except Exception:
            # Tactical safety posture: if the primary gate fails, fail closed.
            logger.exception("Action gate evaluation failed; defaulting to high-stakes handling")
            return True

        # Unknown gate interface defaults to high-stakes path for safety.
        logger.warning("Action gate does not expose known API; defaulting high-stakes")
        return True

    def _read_valence(self, proposed_action: ProposedAction) -> float:
        probe = self.emotion_probe
        readers = (
            "get_current_valence",
            "current_valence",
            "read_valence",
            "get_valence",
            "probe",
        )
        for reader_name in readers:
            reader = getattr(probe, reader_name, None)
            if not callable(reader):
                continue
            try:
                return float(reader(proposed_action))
            except TypeError:
                try:
                    return float(reader())
                except Exception:
                    logger.exception("Emotion probe '%s' failed without action context", reader_name)
            except Exception:
                logger.exception("Emotion probe '%s' failed", reader_name)

        if isinstance(proposed_action, Mapping) and "valence" in proposed_action:
            return float(proposed_action["valence"])

        logger.warning("Emotion probe does not expose known API; using neutral valence")
        return 0.0

    def _apply_deliberation_boost(self, proposed_action: ProposedAction) -> bool:
        steering = self.emotion_steering
        appliers = ("apply", "apply_steering", "apply_mode", "steer")
        for method_name in appliers:
            method = getattr(steering, method_name, None)
            if not callable(method):
                continue
            try:
                result = method(
                    "deliberation_boost",
                    proposed_action=proposed_action,
                    reason="overconfidence_detected",
                )
                return self._coerce_applier_result(result)
            except TypeError:
                try:
                    result = method("deliberation_boost")
                    return self._coerce_applier_result(result)
                except Exception:
                    logger.exception("Emotion steering '%s' failed", method_name)
            except Exception:
                logger.exception("Emotion steering '%s' failed", method_name)
        logger.warning("Emotion steering does not expose known API; continuing without steering")
        return False

    @staticmethod
    def _coerce_applier_result(result: Any) -> bool:
        if isinstance(result, Mapping):
            if "applied" in result:
                return bool(result["applied"])
            return bool(result)
        if result is None:
            return True
        return bool(result)

    def _generate_reasoning(self, proposed_action: ProposedAction, prompt: str) -> tuple[str, bool]:
        generator = self._resolve_reasoning_generator(proposed_action)
        if generator is None:
            return self._extract_precomputed_deliberation(proposed_action), False

        payload = self._invoke_reasoning_generator(generator, prompt)
        if isinstance(payload, Mapping):
            for key in ("deliberation_text", "reasoning", "text"):
                if key in payload and str(payload[key]).strip():
                    return str(payload[key]).strip(), True
            return str(payload).strip(), True
        return str(payload).strip(), True

    def _resolve_reasoning_generator(self, proposed_action: ProposedAction) -> Callable[..., Any] | None:
        if isinstance(proposed_action, Mapping):
            for key in ("deliberation_generator", "reasoning_generator", "extended_thinking_fn"):
                candidate = proposed_action.get(key)
                if callable(candidate):
                    return candidate

        for attr_name in ("generate_deliberation", "generate_reasoning", "force_deliberation"):
            candidate = getattr(proposed_action, attr_name, None)
            if callable(candidate):
                return candidate
        return None

    @staticmethod
    def _invoke_reasoning_generator(generator: Callable[..., Any], prompt: str) -> Any:
        attempts = (
            lambda: generator(prompt=prompt, force_extended_thinking=True),
            lambda: generator(prompt, True),
            lambda: generator(prompt),
            lambda: generator(),
        )
        for attempt in attempts:
            try:
                return attempt()
            except TypeError:
                continue
        return generator(prompt=prompt)

    @staticmethod
    def _extract_precomputed_deliberation(proposed_action: ProposedAction) -> str:
        if isinstance(proposed_action, Mapping):
            for key in ("deliberation_text", "reasoning", "extended_thinking"):
                value = proposed_action.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        for attr_name in ("deliberation_text", "reasoning", "extended_thinking"):
            value = getattr(proposed_action, attr_name, None)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _parse_risk_acknowledgment(self, deliberation_text: str) -> tuple[bool, List[str]]:
        if not deliberation_text.strip():
            return False, ["missing_deliberation_reasoning"]

        normalized = " ".join(deliberation_text.lower().split())
        modifications: List[str] = []
        missing_dimensions: List[str] = []
        for dimension, keywords in self._DIMENSION_KEYWORDS.items():
            if not any(keyword in normalized for keyword in keywords):
                missing_dimensions.append(dimension)

        if missing_dimensions:
            modifications.extend([f"missing_{dimension}_analysis" for dimension in missing_dimensions])

        risk_mentioned = any(marker in normalized for marker in self._RISK_MARKERS)
        if not risk_mentioned:
            modifications.append("risk_not_acknowledged")

        if len(normalized) < 80:
            modifications.append("deliberation_too_brief")

        if not missing_dimensions and risk_mentioned and len(normalized) >= 80:
            modifications.append("risk_acknowledged")
            return True, modifications
        return False, modifications

    def _inject_prompt(self, proposed_action: ProposedAction, prompt: str) -> None:
        if isinstance(proposed_action, dict):
            proposed_action["deliberation_prompt"] = prompt
            return
        try:
            setattr(proposed_action, "deliberation_prompt", prompt)
        except Exception:
            logger.debug("Could not attach deliberation prompt to proposed action instance")

    @staticmethod
    def _extract_action_description(proposed_action: ProposedAction) -> str:
        description = ""
        if isinstance(proposed_action, Mapping):
            description = str(
                proposed_action.get("action_description")
                or proposed_action.get("description")
                or proposed_action.get("tool_name")
                or ""
            )
        if not description:
            description = str(getattr(proposed_action, "action_description", "")).strip()
        if not description:
            description = str(getattr(proposed_action, "description", "")).strip()
        if not description:
            description = "unspecified high-stakes action"
        if len(description) > 500:
            description = f"{description[:497]}..."
        return description

    def _resolve_overconfidence_threshold(self) -> float:
        threshold = getattr(self.emotion_probe, "overconfidence_threshold", None)
        if threshold is not None:
            return float(threshold)

        getter = getattr(self.emotion_probe, "get_overconfidence_threshold", None)
        if callable(getter):
            try:
                return float(getter())
            except Exception:
                logger.exception("Failed to read threshold from emotion probe; using default")
        return 0.7

    def _record_valence_sample(self, valence: float) -> None:
        with self._stats_lock:
            self._stats["_valence_sum"] += float(valence)
            self._stats["_valence_samples"] += 1

    def _increment_stat(self, key: str) -> None:
        with self._stats_lock:
            self._stats[key] = float(self._stats[key]) + 1

    @staticmethod
    def _log_intercept(action_description: str, result: InterceptResult, valence: float | None) -> None:
        logger.info(
            "Deliberation intercept completed",
            extra={
                "action_description": action_description,
                "valence": valence,
                "proceed": bool(result["proceed"]),
                "steering_applied": bool(result["steering_applied"]),
                "modifications": list(result["modifications"]),
            },
        )

