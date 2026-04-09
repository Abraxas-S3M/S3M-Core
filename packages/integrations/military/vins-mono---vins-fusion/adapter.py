"""Adapter for VINS-Mono / VINS-Fusion odometry workflows.

Military/tactical context:
This wrapper standardizes visual-inertial odometry readiness so UAV operators
can maintain pose estimation in denied environments without cloud dependence.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class VinsMonoVinsAdapter(IntegrationAdapter):
    """S3M integration adapter for VINS-Mono and VINS-Fusion tactical VIO flows."""

    integration_id = "vins-mono---vins-fusion"
    domain = "military"
    _COMMAND_CANDIDATES = ("vins_node", "vins_estimator", "ros2", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.vins-mono---vins-fusion")

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
        """Validate untrusted VIO request payloads before local execution."""
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
            name=str(raw.get("name", "VINS-Mono / VINS-Fusion")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/HKUST-Aerial-Robotics/VINS-Mono")),
            license=str(raw.get("license", "(BSD-style)")),
            description=str(
                raw.get("description")
                or "Robust visual-inertial odometry for autonomous UAV motion estimation."
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["visual_inertial_odometry", "state_estimation", "gps_denied_pose_tracking"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["python3", "ros2"]),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path", "")),
        )

    def validate_availability(self) -> bool:
        """Validate local VINS runtime availability for sovereign deployments."""
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
        """Wrap VIO operation with deterministic fixture fallback for mission drills."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation", "vio_status")).strip().lower()

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning fixture for VINS mission rehearsal.")
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
                "error": "VINS-Mono / VINS-Fusion is not installed or configured",
                "request": safe_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "available": True,
            # Tactical safety policy: wrapper validates runtime only.
            "message": "VINS runtime detected; live odometry execution is delegated to local autonomy stack.",
            "request": safe_params,
        }
