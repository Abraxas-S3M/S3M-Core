"""Adapter for AirSim autonomous platform simulation workflows.

Military/tactical context:
This wrapper standardizes AirSim mission stepping and telemetry snapshots so UAV
teams can rehearse autonomous tactics in sovereign airgapped facilities.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AirsimAdapter(IntegrationAdapter):
    """S3M simulation adapter for AirSim."""

    integration_id = "airsim"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("airsim", "python3", "unreal")
    _MODULE_CANDIDATES = ("airsim",)

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.airsim")

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
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(data, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    def get_manifest(self) -> IntegrationManifest:
        """Return AirSim manifest metadata for simulation cataloging."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "AirSim"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/microsoft/AirSim"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Photorealistic simulator for drones, cars, and autonomous systems."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["vehicle_telemetry_capture", "sensor_stream_simulation", "autonomy_loop_rehearsal"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["airsim"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check if local AirSim runtime components are available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        if any(shutil.which(command) for command in self._COMMAND_CANDIDATES):
            return True

        return any(importlib.util.find_spec(module_name) for module_name in self._MODULE_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute AirSim operation with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("params must be a dictionary")

        operation = request.get("operation", "telemetry_snapshot")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic telemetry payloads for after-action comparison.
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
                "operation": operation,
                "error": "AirSim is not installed or configured in this environment",
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "AirSim local runtime detected; external API calls remain disabled by policy.",
        }
