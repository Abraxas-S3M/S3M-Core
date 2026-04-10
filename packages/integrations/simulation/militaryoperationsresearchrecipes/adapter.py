"""Adapter for MilitaryOperationsResearchRecipes simulation workflows.

Military/tactical context:
This wrapper lets S3M planners run deterministic war-gaming checks for
methods and models for military operations research and optimization in disconnected command environments.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MilitaryoperationsresearchrecipesAdapter(IntegrationAdapter):
    """S3M simulation adapter for MilitaryOperationsResearchRecipes."""

    integration_id = "militaryoperationsresearchrecipes"
    domain = "simulation"
    _COMMAND_CANDIDATES = ('python3', 'python', 'jupyter')

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate mission payloads before simulation orchestration."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 25000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for simulation mission planning."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "MilitaryOperationsResearchRecipes"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/eidelen/MilitaryOperationsResearchRecipes"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(raw.get("description") or "Methods and models for military operations research and optimization"),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(raw.get("capabilities") or ['logistics_optimization', 'force_allocation_modeling', 'operational_research_workflow']),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if local simulation tooling exists on this sovereign node."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN").strip()
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        return any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute simulation bridge with deterministic fixture replay offline."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "optimization_recipe").strip().lower()

        if self.is_airgapped:
            self.logger.info("Returning fixture output for simulation operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
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
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "militaryoperationsresearchrecipes runtime is not installed on this sovereign node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "MilitaryOperationsResearchRecipes adapter is available for local simulation orchestration.",
        }
