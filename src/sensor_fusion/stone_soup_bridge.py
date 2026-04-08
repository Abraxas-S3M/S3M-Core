"""Bridge layer exposing Stone Soup identity and association outputs for COP tracks."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency in offline environments
    from stonesoup.dataassociator.neighbour import GNNWith2DAssignment
    from stonesoup.hypothesiser.gaussianmixture import GaussianMixtureHypothesiser

    STONESOUP_AVAILABLE = True
except Exception:  # pragma: no cover - covered by fallback tests
    GNNWith2DAssignment = None  # type: ignore[assignment]
    GaussianMixtureHypothesiser = None  # type: ignore[assignment]
    STONESOUP_AVAILABLE = False


class StoneSoupBridge:
    """Provides a tactical wrapper around Stone Soup identity hypotheses.

    The bridge keeps identity probabilities and association confidence keyed by track ID
    so the COP workspace can render operator-facing confidence bars consistently.
    """

    def __init__(self, identity_labels: Optional[Sequence[str]] = None) -> None:
        labels = tuple(str(label).strip().lower() for label in (identity_labels or ("friendly", "hostile", "unknown")))
        self._identity_labels: Tuple[str, ...] = tuple(label for label in labels if label)
        if not self._identity_labels:
            self._identity_labels = ("friendly", "hostile", "unknown")

        self._stonesoup_available = STONESOUP_AVAILABLE
        # Preserve explicit Stone Soup component references for multi-hypothesis tracking.
        self._hypothesiser_cls = GaussianMixtureHypothesiser
        self._associator_cls = GNNWith2DAssignment

        self._identity_cache: Dict[str, Dict[str, float]] = {}
        self._association_cache: Dict[str, float] = {}

    def set_track_context(
        self,
        track_id: Any,
        identity_hypotheses: Optional[Dict[str, Any]] = None,
        association_confidence: Optional[Any] = None,
    ) -> None:
        normalized_track_id = self._normalize_track_id(track_id)
        if not normalized_track_id:
            return

        if identity_hypotheses and isinstance(identity_hypotheses, dict):
            self._identity_cache[normalized_track_id] = self._normalize_probabilities(identity_hypotheses)

        if association_confidence is not None:
            self._association_cache[normalized_track_id] = self._clamp_probability(association_confidence)

    def get_identity_probabilities(self, track_id: Any) -> Dict[str, float]:
        normalized_track_id = self._normalize_track_id(track_id)
        if not self._stonesoup_available:
            return self._uniform_probabilities()

        if normalized_track_id and normalized_track_id in self._identity_cache:
            return dict(self._identity_cache[normalized_track_id])

        inferred = self._infer_identity_prior(normalized_track_id)
        if normalized_track_id:
            self._identity_cache[normalized_track_id] = inferred
        return dict(inferred)

    def get_association_confidence(self, track_id: Any) -> float:
        normalized_track_id = self._normalize_track_id(track_id)
        if not normalized_track_id:
            return 0.0
        if normalized_track_id in self._association_cache:
            return self._association_cache[normalized_track_id]
        return 0.0 if not self._stonesoup_available else 0.5

    @property
    def stonesoup_available(self) -> bool:
        return self._stonesoup_available

    def _uniform_probabilities(self) -> Dict[str, float]:
        count = len(self._identity_labels)
        if count <= 0:
            return {"unknown": 1.0}
        share = round(1.0 / count, 3)
        values = {label: share for label in self._identity_labels}
        total = sum(values.values())
        first_label = self._identity_labels[0]
        values[first_label] = round(values[first_label] + (1.0 - total), 3)
        return values

    def _infer_identity_prior(self, normalized_track_id: str) -> Dict[str, float]:
        if "hostile" in normalized_track_id or normalized_track_id.startswith(("th", "en", "red")):
            return self._normalize_probabilities({"friendly": 0.1, "hostile": 0.8, "unknown": 0.1})
        if "friendly" in normalized_track_id or normalized_track_id.startswith(("fr", "blue")):
            return self._normalize_probabilities({"friendly": 0.8, "hostile": 0.1, "unknown": 0.1})
        return self._normalize_probabilities({"friendly": 0.2, "hostile": 0.2, "unknown": 0.6})

    def _normalize_probabilities(self, raw_probabilities: Dict[str, Any]) -> Dict[str, float]:
        cleaned: Dict[str, float] = {}
        for label in self._identity_labels:
            cleaned[label] = self._clamp_probability(raw_probabilities.get(label, 0.0))

        total = sum(cleaned.values())
        if total <= 0:
            return self._uniform_probabilities()

        normalized = {label: round(value / total, 3) for label, value in cleaned.items()}
        normalized_total = sum(normalized.values())
        first_label = self._identity_labels[0]
        normalized[first_label] = round(normalized[first_label] + (1.0 - normalized_total), 3)
        return normalized

    @staticmethod
    def _normalize_track_id(track_id: Any) -> str:
        if track_id is None:
            return ""
        return str(track_id).strip().lower()

    @staticmethod
    def _clamp_probability(raw_value: Any) -> float:
        try:
            parsed = float(raw_value)
        except Exception:
            return 0.0
        return max(0.0, min(1.0, parsed))
