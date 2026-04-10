"""Adapter for DoppelGANger synthetic time-series simulation integration.

Military/tactical context:
This wrapper supports generation of synthetic temporal mission telemetry so
operators can rehearse campaign timelines while keeping sensitive sensor and
operations logs inside sovereign, disconnected infrastructure.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class DoppelgangerAdapter(IntegrationAdapter):
    """S3M simulation adapter for DoppelGANger."""

    integration_id = "doppelganger"
    domain = "simulation"
    _MODULE_CANDIDATES = ("doppelganger", "tensorflow")
    _COMMAND_CANDIDATES = ("python3",)
    _SUPPORTED_OPERATIONS = {"train", "sample_sequence", "health_probe"}

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
        """Validate temporal simulation requests for secure replay workflows."""
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
            name=str(raw.get("name") or "DoppelGANger"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/fjxmlzn/DoppelGANger"),
            license=str(raw.get("license") or "(Open)"),
            description=str(
                raw.get("description")
                or "GAN framework for synthetic time-series mission and telemetry data."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["time_series_generation", "sequence_conditioning", "telemetry_scenario_replay"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local DoppelGANger availability on sovereign compute nodes."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("DOPPELGANGER_PATH").strip()
        if configured_path:
            return Path(configured_path).expanduser().exists()

        configured_bin = self._env("DOPPELGANGER_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        module_ready = any(importlib.util.find_spec(name) is not None for name in self._MODULE_CANDIDATES)
        command_ready = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return module_ready or command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute DoppelGANger orchestration with fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "sample_sequence").strip().lower()
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
            self.logger.info("Airgapped mode active; returning DoppelGANger fixture for %s", operation)
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
                "message": "DoppelGANger runtime is not installed on this sovereign node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "DoppelGANger runtime is available for local synthetic time-series simulation workloads.",
        }
