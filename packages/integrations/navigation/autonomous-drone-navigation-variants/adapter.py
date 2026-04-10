"""Adapter for GPS-denied autonomous drone navigation variants.

Military/tactical context:
This wrapper standardizes availability checks and offline fixture replay for
multiple drone navigation pipelines used in contested electromagnetic terrain.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AutonomousDroneNavigationvariantsAdapter(IntegrationAdapter):
    """S3M adapter for autonomous drone navigation variants."""

    integration_id = "autonomous-drone-navigation-variants"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("ros2", "px4", "python3")
    _DEFAULT_OPERATION = "evaluate_gps_denied_route"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.navigation.autonomous-drone-navigation-variants"
        )

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
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}

        if not isinstance(raw, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return adapter metadata for tactical orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Autonomous-drone-navigation (variants)")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/topics/gps-denied")),
            license=str(raw.get("license", "Varies")),
            description=str(
                raw.get(
                    "description",
                    "GPS-denied drone navigation variants using optical flow, visual odometry, and sensor fusion.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get(
                    "capabilities",
                    ["gps_denied_navigation", "optical_flow_fusion", "contested_zone_localization"],
                )
            ),
            system_dependencies=self._coerce_list(
                raw.get("system_dependencies", ["ros2", "python3"])
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime clues without making external network calls."""
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
        """Execute wrapper request with deterministic airgapped fixture mode."""
        if params is None:
            request: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError(
                "params must be a dictionary for secure GPS-denied mission execution."
            )
        else:
            request = params

        operation = str(request.get("operation", self._DEFAULT_OPERATION))
        if self.is_airgapped:
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "Navigation variant runtime is not installed or configured on this node.",
                "request": request,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request,
            "note": "Navigation variant checks passed for offline tactical mission planning.",
        }
