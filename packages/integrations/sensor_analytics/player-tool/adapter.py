"""Adapter for player-tool maritime surveillance workflows.

Military/tactical context:
This wrapper supports sovereign maritime awareness by validating local
simulation and data-fusion tool readiness for patrol planning and anomaly
detection in disconnected command environments.
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


class PlayerToolAdapter(IntegrationAdapter):
    """S3M adapter for player-tool maritime surveillance workflows."""

    integration_id = "player-tool"
    domain = "sensor_analytics"

    _COMMAND_CANDIDATES = ("player-tool", "python3")
    _MODULE_CANDIDATES = ("player_tool",)
    _DEFAULT_OPERATION = "simulate_maritime_surveillance"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_analytics.player-tool")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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
        if not isinstance(loaded, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return loaded

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure maritime simulation execution.")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for tactical maritime-surveillance orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "player-tool")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/alvarolb/player-tool")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Open-source maritime surveillance simulation and multi-sensor data fusion tooling.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    [
                        "maritime_surveillance_simulation",
                        "multi_sensor_data_fusion",
                        "patrol_pattern_evaluation",
                    ],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime readiness without external API calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        module_ready = any(importlib.util.find_spec(name) for name in self._MODULE_CANDIDATES)
        command_ready = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return module_ready or command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper logic with deterministic airgapped fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation", self._DEFAULT_OPERATION))

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "player-tool dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "Local readiness checks passed; maritime simulation execution remains policy-controlled.",
        }
