"""Adapter for M3DGR multi-sensor SLAM workflows.

Military/tactical context:
This wrapper supports fused LiDAR-camera-IMU localization readiness checks
for sovereign battlefield navigation stacks operating without cloud links.
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


class M3dgrAdapter(IntegrationAdapter):
    """S3M sensor-fusion adapter for M3DGR data and fusion readiness."""

    integration_id = "m3dgr"
    domain = "sensor_fusion"
    _COMMAND_CANDIDATES = ("python3", "ros2", "m3dgr")
    _MODULE_CANDIDATES = ("torch", "numpy")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.m3dgr")

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
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate mission payload before fused SLAM task dispatch."""
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
        """Return M3DGR metadata for tactical fusion orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "M3DGR"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/sjtuyinjie/M3DGR"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Multi-sensor multi-scenario SLAM dataset and Ground-Fusion++ framework."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get("capabilities")
                or [
                    "lidar-visual-inertial-fusion",
                    "ground-fusion-benchmarking",
                    "slam-readiness-validation",
                ]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local M3DGR dependencies for disconnected deployment."""
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
        """Execute fused-SLAM wrapper flow with fixture fallback in airgap."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "fusion_slam_snapshot")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning M3DGR fixture payload.")
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
                "message": "M3DGR runtime dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local M3DGR checks passed; live fusion execution remains mission-policy controlled.",
        }
