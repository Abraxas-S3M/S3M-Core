"""Adapter for aircraft engine RUL estimation workflows.

Military/tactical context:
The wrapper gives maintenance command cells deterministic RUL estimates to
prioritize repairs and preserve sortie generation in austere theaters.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PredictiveMaintenanceProjectAdapter(IntegrationAdapter):
    """S3M wrapper for Predictive_Maintenance_Project capabilities."""

    integration_id = "predictive-maintenance-project"
    domain = "maintenance"
    _COMMAND_CANDIDATES = ("python3", "python")
    _MODULE_CANDIDATES = ("numpy", "pandas", "sklearn")
    _SUPPORTED_OPERATIONS = {"rul_estimate", "degradation_trend", "mission_readiness"}

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.maintenance.predictive-maintenance-project")

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
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate payloads before mission sustainment decision support."""
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
        """Return manifest metadata for orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Predictive_Maintenance_Project"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/SureshAthanti/Predictive_Maintenance_Project"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Remaining Useful Life prediction workflows for turbofan engines."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["rul_estimation", "degradation_tracking", "maintenance_window_planning"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check for local predictive-maintenance runtime availability."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        module_available = any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES)
        command_available = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute predictive-maintenance project wrapper safely offline."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "rul_estimate").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning fixture for operation=%s", operation)
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
                "message": "Predictive_Maintenance_Project dependencies are not installed.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local RUL tooling detected; orchestrator may proceed with mission sustainment analysis.",
        }
