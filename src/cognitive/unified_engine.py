"""Unified cognitive decision engine for contested tactical autonomy."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class UnifiedSelection:
    """Selected mission option and its normalized utility."""

    option: Any
    utility_score: float


@dataclass(frozen=True)
class UnifiedDecisionRecord:
    """Decision metadata used by runtime governance and human review gates."""

    selected: UnifiedSelection
    confidence: float
    requires_human_review: bool = False


@dataclass(frozen=True)
class UnifiedDecisionResult:
    """Decision result contract expected by the runtime cognitive loop."""

    result: UnifiedDecisionRecord
    backend: str


class UnifiedCognitiveEngine:
    """
    Single decision facade that hides distributed/optional backend differences.

    This keeps command logic deterministic during tactical degradation by
    always returning a normalized decision object even when richer engines are
    unavailable on the edge node.
    """

    def __init__(
        self,
        decision_engine: Optional[Any] = None,
        min_decision_confidence: float = 0.0,
    ) -> None:
        self.decision_engine = decision_engine
        self.min_decision_confidence = max(0.0, min(1.0, float(min_decision_confidence)))

    def evaluate(
        self,
        options: Sequence[Any],
        belief_state: Optional[Any] = None,
        author_id: Optional[str] = None,
        decision_engine: Optional[Any] = None,
    ) -> Optional[Any]:
        """
        Return a normalized decision payload using backend if available.

        The backend is optional so the node can continue making bounded,
        deterministic decisions while disconnected from heavier components.
        """
        option_list = list(options or [])
        if not option_list:
            return None

        backend = decision_engine if decision_engine is not None else self.decision_engine
        if backend is not None and hasattr(backend, "evaluate"):
            try:
                backend_result = backend.evaluate(
                    options=option_list,
                    belief_state=belief_state,
                    author_id=author_id,
                )
                if self._looks_like_decision_result(backend_result):
                    return backend_result
                normalized = self._normalize_backend_result(backend_result, option_list)
                if normalized is not None:
                    return normalized
            except Exception:
                # Fall through to deterministic fallback if backend faults.
                pass

        return self._fallback_decision(option_list)

    @staticmethod
    def _looks_like_decision_result(result: Any) -> bool:
        return bool(
            result is not None
            and hasattr(result, "result")
            and hasattr(result.result, "selected")
            and hasattr(result.result, "confidence")
        )

    def _normalize_backend_result(
        self,
        backend_result: Any,
        options: Sequence[Any],
    ) -> Optional[UnifiedDecisionResult]:
        confidence = self._extract_float(getattr(backend_result, "confidence", None))
        selected = getattr(backend_result, "selected", None)
        if selected is None:
            return None

        selected_option = getattr(selected, "option", selected)
        selected_option = self._coerce_option(selected_option, options)
        utility = self._extract_float(
            getattr(selected, "utility_score", getattr(backend_result, "utility_score", None)),
            default=0.0,
        )
        confidence_val = confidence if confidence is not None else 0.0
        return UnifiedDecisionResult(
            result=UnifiedDecisionRecord(
                selected=UnifiedSelection(option=selected_option, utility_score=utility),
                confidence=confidence_val,
                requires_human_review=confidence_val < self.min_decision_confidence,
            ),
            backend="normalized_backend",
        )

    def _fallback_decision(self, options: Sequence[Any]) -> UnifiedDecisionResult:
        scored = [(self._option_score(opt), idx, self._coerce_option(opt, options)) for idx, opt in enumerate(options)]
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        score, _, selected_option = scored[0]
        confidence = max(0.0, min(1.0, score))
        return UnifiedDecisionResult(
            result=UnifiedDecisionRecord(
                selected=UnifiedSelection(option=selected_option, utility_score=score),
                confidence=confidence,
                requires_human_review=confidence < self.min_decision_confidence,
            ),
            backend="deterministic_fallback",
        )

    def _coerce_option(self, option: Any, options: Sequence[Any]) -> Any:
        if option is None:
            option = options[0]
        if hasattr(option, "label"):
            return option
        if isinstance(option, dict):
            label = str(option.get("label", "option"))
            probability = self._extract_float(option.get("probability_of_success"), default=0.0)
            return SimpleNamespace(
                label=label,
                probability_of_success=probability,
                raw=option,
            )
        return SimpleNamespace(label=str(option), probability_of_success=0.0, raw=option)

    def _option_score(self, option: Any) -> float:
        probability = self._extract_float(self._read_key(option, "probability_of_success"), default=0.0)
        confidence_hint = self._extract_float(self._read_key(option, "confidence"), default=0.0)
        utility_hint = self._extract_float(self._read_key(option, "utility_score"), default=0.0)
        score = (0.60 * probability) + (0.25 * confidence_hint) + (0.15 * utility_hint)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _read_key(option: Any, key: str) -> Any:
        if isinstance(option, dict):
            return option.get(key)
        return getattr(option, key, None)

    @staticmethod
    def _extract_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        try:
            return float(value)
        except Exception:
            return default
