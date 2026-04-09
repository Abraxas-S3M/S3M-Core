"""Adapter for Autonomous-Ai-drone-scripts.

Military/tactical context:
This wrapper provides deterministic mission-rehearsal outputs for sovereign
deployments where UAV/UGV autonomy tools must operate in disconnected,
security-constrained environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AutonomousAiDroneScriptsAdapter(IntegrationAdapter):
    """S3M integration adapter for Autonomous-Ai-drone-scripts."""

    integration_id = "autonomous-ai-drone-scripts"
    domain = "military"
    _COMMAND_CANDIDATES = ('python3', 'mavproxy.py', 'arducopter')

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.autonomous-ai-drone-scripts")

    @property
    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}

        try:
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}

        if not isinstance(payload, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for tactical orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Autonomous-Ai-drone-scripts")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/sieuwe1/Autonomous-Ai-drone-scripts")),
            license=str(raw.get("license", "MIT")),
            description=str(raw.get("description", "AI-powered autonomous multirotor navigation and obstacle avoidance for low-latency tactical flight operations.")),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=[str(item) for item in raw.get("capabilities", ['autonomous-navigation', 'obstacle-avoidance', 'multirotor-control'])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime availability without any external API dependencies."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def _sanitize_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for safe tactical execution.")

        sanitized: dict[str, Any] = {}
        for key, value in params.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            elif isinstance(value, list):
                sanitized[key] = [
                    item for item in value if isinstance(item, (str, int, float, bool))
                ]
        return sanitized

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap primary mission workflow with deterministic airgapped fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "autonomous_patrol")

        if self.is_airgapped:
            self.logger.info(
                "Airgapped mode active; returning fixture response for tactical rehearsal."
            )
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "available": self.validate_availability(),
                "result": self._read_fixture("sample_response.json"),
                "request": safe_params,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "error": "autonomous-ai-drone-scripts runtime is not installed or configured",
                "request": safe_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "available": True,
            "request": safe_params,
            "note": (
                "Local runtime validated; live execution is delegated to mission controllers "
                "on sovereign infrastructure."
            ),
        }
