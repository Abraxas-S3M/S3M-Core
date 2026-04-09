"""Adapter for PX4-Autopilot mission-flight workflows.

Military/tactical context:
This wrapper validates autonomous UAV flight-control readiness for mission
sorties where sovereign command infrastructure cannot depend on cloud services.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Px4AutopilotAdapter(IntegrationAdapter):
    """S3M integration adapter for PX4 mission autopilot orchestration."""

    integration_id = "px4-autopilot"
    domain = "military"
    _COMMAND_CANDIDATES = ("px4", "px4-sitl", "make", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.px4-autopilot")

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

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted flight-task parameters before local processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        safe_payload = json.loads(json.dumps(params))
        if len(json.dumps(safe_payload)) > 25000:
            raise ValueError("params payload is too large")
        return safe_payload

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata loaded from local manifest.yaml."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "PX4-Autopilot")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/PX4/PX4-Autopilot")),
            license=str(raw.get("license", "BSD-3-Clause")),
            description=str(
                raw.get("description")
                or "Leading open-source autopilot for autonomous drones and UAVs."
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["autopilot_control", "mission_navigation", "failsafe_management"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["python3", "make"]),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path", "")),
        )

    def validate_availability(self) -> bool:
        """Validate local PX4 runtime readiness without network dependencies."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap PX4 sortie-control operation with deterministic fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation", "autopilot_status")).strip().lower()

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning fixture for PX4 mission rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "status": "ok",
                "available": True,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "error": "PX4-Autopilot is not installed or configured",
                "request": safe_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "available": True,
            # Tactical safety policy: wrapper only reports readiness in sovereign mode.
            "message": "PX4 runtime detected; live mission execution is delegated to approved control loops.",
            "request": safe_params,
        }
