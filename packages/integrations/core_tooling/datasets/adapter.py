"""Adapter for Hugging Face Datasets processing pipelines.

Military/tactical context:
This wrapper verifies local dataset ingestion tooling so sovereign training
corpora can be staged, filtered, and cached for mission model updates without
reaching any external network service.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class DatasetsAdapter(IntegrationAdapter):
    """S3M core tooling adapter for Hugging Face Datasets."""

    integration_id = "datasets"
    domain = "core_tooling"
    _COMMAND_CANDIDATES = ("datasets-cli",)
    _PYTHON_MODULE_CANDIDATES = ("datasets",)

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Failed to parse manifest YAML at %s", manifest_path)
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
        """Validate dataset pipeline payloads before local runtime dispatch."""
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
        """Return wrapper metadata used by tactical integration discovery."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "Datasets"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/huggingface/datasets"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Dataset loading and transformation runtime for sovereign training pipelines."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["dataset-loading", "dataset-processing", "offline-caching"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies") or ["datasets"]),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if datasets runtime is installed on this sovereign node."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("DATASETS_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env("DATASETS_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        if any(importlib.util.find_spec(module_name) for module_name in self._PYTHON_MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute dataset tooling wrapper with deterministic fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "dataset_pipeline").strip().lower()

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning datasets fixture for operation=%s", operation)
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
                "message": "datasets is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "datasets runtime checks passed for local data ingestion workflows.",
        }
