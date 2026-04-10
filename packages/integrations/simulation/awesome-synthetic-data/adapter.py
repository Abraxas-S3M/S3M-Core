"""Adapter for awesome-synthetic-data simulation reference integration.

Military/tactical context:
This wrapper exposes a curated synthetic-data knowledge reference so planning
teams can quickly identify offline-capable generation tools that strengthen
simulation and training readiness in denied-network environments.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeSyntheticDataAdapter(IntegrationAdapter):
    """S3M simulation adapter for awesome-synthetic-data."""

    integration_id = "awesome-synthetic-data"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("git",)
    _SUPPORTED_OPERATIONS = {"catalog_lookup", "curation_summary", "health_probe"}

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Failed to parse manifest: %s", manifest_path)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate catalog-query requests for deterministic tactical lookups."""
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
        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return adapter metadata used by tactical orchestrator discovery."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-synthetic-data"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/statice/awesome-synthetic-data"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Curated list of synthetic data tools and resources for simulation planning."
            ),
            integration_type=str(raw.get("integration_type") or "reference"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["tool_catalog_reference", "synthetic_data_landscape_scan", "offline_resource_indexing"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local catalog availability for simulation planning cells."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("AWESOME_SYNTHETIC_DATA_PATH").strip()
        if configured_path:
            return Path(configured_path).expanduser().exists()

        vendor_path = self.get_manifest().vendor_path.strip()
        if vendor_path and Path(vendor_path).expanduser().exists():
            return True

        return any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute reference-catalog lookup with fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "catalog_lookup").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "adapter",
                "status": "error",
                "error": f"unsupported operation: {operation}",
                "supported_operations": sorted(self._SUPPORTED_OPERATIONS),
                "request": safe_params,
            }

        if self.is_airgapped:
            self.logger.info(
                "Airgapped mode active; returning awesome-synthetic-data fixture for operation=%s",
                operation,
            )
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
                "message": "awesome-synthetic-data reference catalog is not available on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "awesome-synthetic-data reference catalog is available for local simulation planning.",
        }
