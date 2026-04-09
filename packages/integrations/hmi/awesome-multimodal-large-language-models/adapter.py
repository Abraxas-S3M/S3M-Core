"""Adapter for Awesome-Multimodal-Large-Language-Models-for-UAV resources.

Military/tactical context:
This wrapper supports offline review of UAV-focused multimodal LLM references
so reconnaissance and targeting support teams can shortlist perception models
under sovereign and disconnected operating conditions.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeMultimodalLargeLanguageAdapter(IntegrationAdapter):
    """S3M integration adapter for UAV multimodal LLM curated resources."""

    integration_id = "awesome-multimodal-large-language-models"
    domain = "hmi"
    _COMMAND_CANDIDATES = ("git", "python3")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _as_list(value: Any) -> list[str]:
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
            self.logger.exception("Manifest parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest must be a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata from local manifest.yaml."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Awesome-Multimodal-Large-Language-Models-for-UAV")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Curated UAV vision-language perception resources for multimodal LLM mission analysis.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._as_list(
                raw.get("capabilities", ["uav_model_reference", "perception_stack_shortlisting", "offline_index_review"])
            ),
            pip_dependencies=self._as_list(raw.get("pip_dependencies")),
            system_dependencies=self._as_list(raw.get("system_dependencies")),
            docker_dependencies=self._as_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path", "")),
        )

    def validate_availability(self) -> bool:
        """Check whether local curated-resource tooling or path is available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run UAV resource wrapper flow with deterministic fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of tactical HMI options.")

        operation = str(request_params.get("operation", "list_uav_multimodal_resources")).strip().lower()
        if not operation:
            raise ValueError("operation cannot be empty.")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving UAV multimodal fixture data.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
                "request": request_params,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "awesome-multimodal-large-language-models resources are not installed or configured",
                "request": request_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local UAV multimodal references validated; analysts can proceed with model triage.",
        }
