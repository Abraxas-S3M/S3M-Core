"""Adapter for awesome-machine-learning-interpretability.

Military/tactical context:
This wrapper enables sovereign human-machine teaming workflows on airgapped
S3M nodes while preserving deterministic behavior for mission rehearsal.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeMachineLearningInterpretabilityAdapter(IntegrationAdapter):
    """S3M integration adapter for awesome-machine-learning-interpretability."""

    integration_id = "awesome-machine-learning-interpretabilit"
    domain = "hmi"
    _COMMAND_CANDIDATES = ('git', 'python3')

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: logger namespace must stay stable for after-action audit trails.
        self.logger = logging.getLogger("s3m.integrations.hmi.awesome-machine-learning-interpretabilit")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata used by command orchestration and compliance checks."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-machine-learning-interpretability"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/jphall663/awesome-machine-learning-interpretability"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Curated responsible ML and interpretability resources"
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ['responsible_ml_reference', 'interpretability_pattern_library', 'governance_briefing_support']
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime tooling without external API calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute local wrapper logic with deterministic airgapped fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", "status")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning fixture payload for tactical rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": f"{self.integration_id} is not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "Local tooling detected; network execution remains disabled for sovereign mission security.",
        }
