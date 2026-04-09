"""Adapter for Hunter-UA-Drone.

Military/tactical context:
This wrapper provides sovereign hooks for autonomous counter-UAS mission
rehearsal, enabling defensive drone teams to evaluate intercept planning and
sensor fusion readiness in disconnected operational theaters.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class HunterUaDroneAdapter(IntegrationAdapter):
    """S3M integration adapter for Hunter-UA-Drone."""

    integration_id = "hunter-ua-drone"
    domain = "military"
    _COMMAND_CANDIDATES = ("hunter-uav", "uav-hunter", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.hunter-ua-drone")

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
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(payload, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata for counter-UAS defensive orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Hunter-UA-Drone"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/Ohara124c41/Hunter-UA-Drone"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Autonomous hunter UAV specification and implementation for defensive drone interception."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["counter_uas_rehearsal", "intercept_path_planning", "sensor_fusion_status"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime tooling availability without remote calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap intercept-planning behavior with deterministic fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = str(request.get("operation", "counter_uas_rehearsal")).strip().lower()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")
        if any(char in operation for char in (";", "|", "&", "`", "$", "\n", "\r")):
            raise ValueError("operation contains unsafe characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic anti-drone rehearsal in denied-network environments.
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "hunter-ua-drone is not installed or configured",
                "operation": operation,
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "note": "Local Hunter-UA-Drone tooling detected for sovereign counter-UAS rehearsal workflows.",
        }
