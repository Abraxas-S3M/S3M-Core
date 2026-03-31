"""Anomaly detection pipeline for tactical telemetry in S3M Layer 02."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource

LOGGER = logging.getLogger(__name__)

try:
    from sklearn.ensemble import IsolationForest  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    IsolationForest = None  # type: ignore


class AnomalyDetector:
    """Detect outliers in operational telemetry for cyber/EW early warning."""

    def __init__(self, contamination: float = 0.1, n_estimators: int = 100) -> None:
        if not isinstance(contamination, (float, int)) or not (0 < float(contamination) < 0.5):
            raise ValueError("contamination must be between 0 and 0.5")
        if not isinstance(n_estimators, int) or n_estimators <= 0:
            raise ValueError("n_estimators must be a positive integer")

        self.contamination = float(contamination)
        self.n_estimators = n_estimators
        self.feature_names: List[str] = []
        self.training_samples = 0
        self._trained = False
        self._fallback_stats: Dict[str, List[float]] = {"mean": [], "std": []}
        self._model = None
        self._backend = "zscore"

        if IsolationForest is not None:
            self._model = IsolationForest(
                contamination=self.contamination,
                n_estimators=self.n_estimators,
                random_state=42,
            )
            self._backend = "isolation_forest"
        else:
            LOGGER.warning("scikit-learn unavailable; anomaly detector using Z-score fallback")

    def _validate_data(self, data: List[List[float]]) -> None:
        if not isinstance(data, list) or not data:
            raise ValueError("data must be a non-empty list of feature vectors")
        row_len = None
        for row in data:
            if not isinstance(row, list) or not row:
                raise ValueError("each sample must be a non-empty list")
            if row_len is None:
                row_len = len(row)
            if len(row) != row_len:
                raise ValueError("all feature rows must have equal length")
            for value in row:
                if not isinstance(value, (int, float)):
                    raise ValueError("feature values must be numeric")

    def _compute_zscore_stats(self, data: List[List[float]]) -> None:
        cols = len(data[0])
        means: List[float] = []
        stds: List[float] = []
        for idx in range(cols):
            values = [float(row[idx]) for row in data]
            mean = sum(values) / len(values)
            variance = sum((val - mean) ** 2 for val in values) / max(1, len(values))
            std = variance ** 0.5
            means.append(mean)
            stds.append(std if std > 1e-8 else 1.0)
        self._fallback_stats = {"mean": means, "std": stds}

    def _category_from_features(self, feature_names: List[str]) -> ThreatCategory:
        lower = " ".join(feature_names).lower()
        if any(token in lower for token in ["rf", "spectrum", "jam", "signal", "carrier"]):
            return ThreatCategory.ELECTRONIC_WARFARE
        if any(token in lower for token in ["packet", "ip", "port", "latency", "throughput", "network"]):
            return ThreatCategory.CYBER
        return ThreatCategory.CYBER

    def fit(self, data: List[List[float]]) -> None:
        """Train baseline model on normal behavior telemetry."""
        self._validate_data(data)
        self.training_samples = len(data)

        if self._backend == "isolation_forest" and self._model is not None:
            self._model.fit(data)
        else:
            self._compute_zscore_stats(data)
        self._trained = True

    def detect(
        self,
        data: List[List[float]],
        feature_names: Optional[List[str]] = None,
    ) -> List[ThreatEvent]:
        """Detect anomalies and convert them to tactical threat events."""
        self._validate_data(data)
        if feature_names is not None:
            if not isinstance(feature_names, list) or any(not isinstance(name, str) for name in feature_names):
                raise ValueError("feature_names must be a list of strings")
            if len(feature_names) != len(data[0]):
                raise ValueError("feature_names length must match feature vector width")
            self.feature_names = feature_names
        elif not self.feature_names:
            self.feature_names = [f"feature_{idx}" for idx in range(len(data[0]))]

        if not self._trained:
            self.fit(data)
            return []

        anomalies: List[ThreatEvent] = []
        category = self._category_from_features(self.feature_names)

        if self._backend == "isolation_forest" and self._model is not None:
            labels = self._model.predict(data)  # -1 anomaly, +1 normal
            scores = self._model.decision_function(data)
            for idx, (sample, label, score) in enumerate(zip(data, labels, scores)):
                if int(label) != -1:
                    continue
                confidence = max(0.5, min(1.0, 0.5 + abs(float(score))))
                anomalies.append(
                    ThreatEvent(
                        source=ThreatSource.ANOMALY_DETECTION,
                        level=ThreatLevel.HIGH if confidence > 0.75 else ThreatLevel.MEDIUM,
                        category=category,
                        timestamp=datetime.now(timezone.utc),
                        title=f"Telemetry anomaly detected (sample {idx})",
                        description=(
                            "Anomalous telemetry pattern detected that may indicate "
                            "adversary cyber intrusion or EW interference."
                        ),
                        raw_data={
                            "sample_index": idx,
                            "values": sample,
                            "feature_names": self.feature_names,
                            "anomaly_score": float(score),
                            "backend": self._backend,
                        },
                        confidence=confidence,
                        recommended_action=(
                            "Correlate with IDS/SIEM and verify affected communication channels immediately."
                        ),
                    )
                )
            return anomalies

        means = self._fallback_stats["mean"]
        stds = self._fallback_stats["std"]
        for idx, sample in enumerate(data):
            zscores = [abs((float(sample[i]) - means[i]) / stds[i]) for i in range(len(sample))]
            max_z = max(zscores)
            if max_z < 3.0:
                continue
            confidence = max(0.5, min(0.99, 0.5 + (max_z - 3.0) / 4.0))
            anomalies.append(
                ThreatEvent(
                    source=ThreatSource.ANOMALY_DETECTION,
                    level=ThreatLevel.HIGH if max_z >= 4.5 else ThreatLevel.MEDIUM,
                    category=category,
                    timestamp=datetime.now(timezone.utc),
                    title=f"Telemetry anomaly detected (sample {idx})",
                    description=(
                        "Z-score outlier detected in tactical telemetry baseline; investigate for hostile activity."
                    ),
                    raw_data={
                        "sample_index": idx,
                        "values": sample,
                        "feature_names": self.feature_names,
                        "zscores": zscores,
                        "max_z": max_z,
                        "backend": self._backend,
                    },
                    confidence=confidence,
                    recommended_action="Validate sensor integrity and isolate suspicious network segments.",
                )
            )
        return anomalies

    def detect_from_csv(self, filepath: str, feature_columns: List[str]) -> List[ThreatEvent]:
        """Load telemetry CSV, fit baseline if needed, then detect anomalies."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        if not isinstance(feature_columns, list) or not feature_columns:
            raise ValueError("feature_columns must be a non-empty list")
        if any(not isinstance(col, str) or not col.strip() for col in feature_columns):
            raise ValueError("feature_columns must contain non-empty strings")

        rows: List[List[float]] = []
        with open(filepath, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    rows.append([float(row[column]) for column in feature_columns])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid CSV row for requested feature columns: {exc}") from exc

        if not rows:
            return []

        if not self._trained:
            self.feature_names = feature_columns
            self.fit(rows)
        return self.detect(rows, feature_names=feature_columns)

    def health_check(self) -> Dict[str, Any]:
        """Report detector readiness for tactical service health endpoints."""
        return {
            "status": "ready" if self._trained else "not_trained",
            "backend": self._backend,
            "features": list(self.feature_names),
            "training_samples": self.training_samples,
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
        }
