"""Adapter for Open-DIS distributed simulation interoperability.

Military/tactical context:
This wrapper standardizes DIS traffic exchange checks so simulation operators
can validate force-level training links in disconnected mission environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenDisAdapter(IntegrationAdapter):
    """S3M adapter for Open-DIS simulation data exchange workflows."""

    integration_id = "open-dis"
    domain = "military"
    _PYTHON_MODULE_CANDIDATES = ("opendis", "open_dis")
    _COMMAND_CANDIDATES = ("open-dis", "dis7", "python3")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(data, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for simulation interoperability orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Open-DIS")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Distributed Interactive Simulation adapter for military simulation interoperability.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=[str(item) for item in raw.get("capabilities", ["dis_protocol", "simulation_sync"])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local Open-DIS capability without external service calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        module_available = any(importlib.util.find_spec(name) is not None for name in self._PYTHON_MODULE_CANDIDATES)
        command_available = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper logic with deterministic fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of tactical integration options.")

        operation = str(request_params.get("operation", "validate_dis_exchange")).strip().lower()
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning Open-DIS fixture for simulation rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": request_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "open-dis tooling is not installed or configured",
                "request": request_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local prerequisites validated; live DIS traffic execution is deployment-specific.",
        }
