"""Adapter for UAV swarm intrusion-detection workflows.

Military/tactical context:
This wrapper supports cyber defense of UAV swarm command links, helping detect
adversarial traffic patterns that could degrade coordinated mission execution.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MachineLearningBasedIntrusionAdapter(IntegrationAdapter):
    """S3M adapter for ML/DL-based UAV swarm IDS workflows."""

    integration_id = "machine-learning-based-intrusion-detecti"
    domain = "sensor_fusion"
    _COMMAND_CANDIDATES = ("python3", "tensorflow", "scikit-learn")
    _DEFAULT_OPERATION = "uav_swarm_intrusion_assessment"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.sensor_fusion.machine-learning-based-intrusion-detecti"
        )

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if any(not isinstance(key, str) for key in normalized):
            raise ValueError("params keys must be strings")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load manifest metadata for tactical UAV swarm cyber defense."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Machine-Learning-Based-Intrusion-Detection-System"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/uamughal/Machine-Learning-Based-Intrusion-Detection-System"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "ML and DL intrusion detection for UAV swarm cyber threat monitoring."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get("capabilities")
                or ["uav_swarm_ids", "model_assisted_alerting", "command_link_anomaly_detection"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local IDS tooling prerequisites without network access."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper request and return deterministic airgapped output."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical requirement: repeatable offline outputs support mission rehearsal.
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "source": "runtime",
                "operation": operation,
                "request": safe_params,
                "message": "UAV IDS runtime dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "accepted",
            "source": "runtime",
            "operation": operation,
            "request": safe_params,
            "message": "Local UAV swarm IDS tooling detected and ready for orchestrated runs.",
        }
