"""
S3M Model Version Controller with rollback and regression checks.

Military/tactical context:
Version gates prevent degraded models from being deployed to operators while
preserving rapid rollback to the last trusted behavior.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class ModelVersion(BaseModel):
    """Metadata for a model version candidate."""

    version_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    version_number: int = 0
    model_name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: Dict[str, float] = Field(default_factory=dict)
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    artifact_path: Optional[str] = None
    status: str = "staged"  # staged | active | rolled_back | archived
    parent_version_id: Optional[str] = None
    notes: str = ""


class ModelVersioner:
    """Thread-safe model version management."""

    _LOWER_IS_BETTER_HINTS = ("loss", "error", "latency", "rmse", "mae", "mse")

    def __init__(
        self,
        model_name: str = "s3m_model",
        storage_dir: Optional[str] = None,
        max_versions: int = 50,
        regression_threshold: float = 0.05,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must be non-empty")
        if max_versions < 5:
            raise ValueError("max_versions must be >= 5")
        if not (0.0 <= regression_threshold <= 1.0):
            raise ValueError("regression_threshold must be in [0, 1]")

        self._model_name = model_name
        self._storage_dir = Path(storage_dir) if storage_dir else None
        self._max_versions = int(max_versions)
        self._regression_threshold = float(regression_threshold)
        self._versions: List[ModelVersion] = []
        self._active_version: Optional[str] = None
        self._lock = threading.RLock()

    def stage(
        self,
        metrics: Dict[str, float],
        config: Optional[Dict[str, Any]] = None,
        artifact_path: Optional[str] = None,
        notes: str = "",
    ) -> ModelVersion:
        if not isinstance(metrics, dict):
            raise TypeError("metrics must be a dictionary")
        numeric_metrics = {
            str(key): float(value)
            for key, value in metrics.items()
            if isinstance(value, (int, float))
        }
        with self._lock:
            version = ModelVersion(
                version_number=len(self._versions) + 1,
                model_name=self._model_name,
                metrics=numeric_metrics,
                config_snapshot=config or {},
                artifact_path=artifact_path,
                status="staged",
                parent_version_id=self._active_version,
                notes=notes,
            )
            self._versions.append(version)
            self._trim_versions()
            return version

    def promote(self, version_id: str) -> Dict[str, Any]:
        with self._lock:
            target = self._find_version(version_id)
            if target is None:
                return {"promoted": False, "regression_detected": False, "details": "Version not found"}
            if target.status != "staged":
                return {
                    "promoted": False,
                    "regression_detected": False,
                    "details": f"Version status is '{target.status}', expected 'staged'",
                }

            regression = False
            details = ""
            if self._active_version:
                baseline = self._find_version(self._active_version)
                if baseline is not None:
                    regression, details = self._check_regression(baseline.metrics, target.metrics)

            if self._active_version:
                current = self._find_version(self._active_version)
                if current is not None:
                    current.status = "archived"

            target.status = "active"
            self._active_version = target.version_id
            return {
                "promoted": True,
                "regression_detected": regression,
                "details": details or f"Version {target.version_number} promoted to active.",
            }

    def rollback(self) -> Dict[str, Any]:
        with self._lock:
            if self._active_version is None:
                return {"rolled_back": False, "details": "No active version"}
            current = self._find_version(self._active_version)
            if current is None or not current.parent_version_id:
                return {"rolled_back": False, "details": "No parent version to roll back to"}
            parent = self._find_version(current.parent_version_id)
            if parent is None:
                return {"rolled_back": False, "details": "Parent version not found"}

            current.status = "rolled_back"
            parent.status = "active"
            self._active_version = parent.version_id
            return {
                "rolled_back": True,
                "details": f"Rolled back from v{current.version_number} to v{parent.version_number}",
                "active_version": parent.version_id,
            }

    def get_active(self) -> Optional[ModelVersion]:
        with self._lock:
            return self._find_version(self._active_version) if self._active_version else None

    def get_history(self) -> List[ModelVersion]:
        with self._lock:
            return list(self._versions)

    def export_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "model_name": self._model_name,
                "max_versions": self._max_versions,
                "regression_threshold": self._regression_threshold,
                "active_version": self._active_version,
                "versions": [version.model_dump() for version in self._versions],
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary")
        with self._lock:
            self._model_name = str(state.get("model_name", self._model_name))
            self._max_versions = int(state.get("max_versions", self._max_versions))
            self._regression_threshold = float(state.get("regression_threshold", self._regression_threshold))
            self._active_version = state.get("active_version")
            self._versions = [ModelVersion.model_validate(item) for item in state.get("versions", [])]
            self._trim_versions()

    def save_state(self, path: Optional[str] = None) -> str:
        output = Path(path) if path else (self._storage_dir / "model_versioner.json" if self._storage_dir else None)
        if output is None:
            raise ValueError("No storage path provided for versioner state")
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output.with_suffix(output.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.export_state(), handle, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(output)
        return str(output)

    def load_from_file(self, path: Optional[str] = None) -> None:
        input_path = Path(path) if path else (self._storage_dir / "model_versioner.json" if self._storage_dir else None)
        if input_path is None:
            raise ValueError("No storage path provided for versioner state")
        if not input_path.exists():
            raise FileNotFoundError(f"Versioner state file not found: {input_path}")
        with input_path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        self.load_state(state)

    def _trim_versions(self) -> None:
        if len(self._versions) <= self._max_versions:
            return
        protected = {self._active_version}
        trimmed: List[ModelVersion] = []
        for version in reversed(self._versions):
            if len(trimmed) >= self._max_versions and version.version_id not in protected:
                continue
            trimmed.append(version)
        self._versions = list(reversed(trimmed))

    def _find_version(self, version_id: Optional[str]) -> Optional[ModelVersion]:
        if not version_id:
            return None
        for version in self._versions:
            if version.version_id == version_id:
                return version
        return None

    def _metric_direction(self, metric_name: str) -> str:
        normalized = metric_name.lower()
        if any(token in normalized for token in self._LOWER_IS_BETTER_HINTS):
            return "lower"
        return "higher"

    def _check_regression(self, baseline: Dict[str, float], candidate: Dict[str, float]) -> Tuple[bool, str]:
        regressions: List[str] = []
        for metric, baseline_value in baseline.items():
            candidate_value = candidate.get(metric)
            if candidate_value is None:
                continue
            direction = self._metric_direction(metric)
            if direction == "higher":
                threshold = baseline_value * (1.0 - self._regression_threshold)
                if baseline_value > 0.0 and candidate_value < threshold:
                    regressions.append(
                        f"{metric}: {candidate_value:.4f} < {baseline_value:.4f} "
                        f"(max drop {self._regression_threshold:.2f})"
                    )
            else:
                threshold = baseline_value * (1.0 + self._regression_threshold)
                if baseline_value >= 0.0 and candidate_value > threshold:
                    regressions.append(
                        f"{metric}: {candidate_value:.4f} > {baseline_value:.4f} "
                        f"(max rise {self._regression_threshold:.2f})"
                    )
        if regressions:
            return True, "Regression detected: " + "; ".join(regressions)
        return False, ""

