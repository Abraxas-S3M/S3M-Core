"""Adapter for the CoFlyers cooperative UAV motion-evaluation platform.

Military/tactical context:
This wrapper supports sovereign rehearsal of cooperative motion algorithms so
operators can evaluate swarm maneuver reliability for multi-UAV missions.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class CoflyersAdapter(IntegrationAdapter):
    """S3M adapter for CoFlyers cooperative swarm-evaluation workflows."""

    integration_id = "coflyers"
    domain = "swarm"
    _DEFAULT_OPERATION = "cooperative_motion_evaluation"
    _COMMAND_CANDIDATES = ("coflyers", "ros2", "gazebo")
    _ENV_PATH_KEYS = ("COFLYERS_PATH", "COFLYERS_ROOT")
    _MODULE_CANDIDATES = ("rclpy",)

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.coflyers")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted planning-request payloads for secure local execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        normalized = json.loads(json.dumps(params))
        if len(json.dumps(normalized)) > 25_000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for tactical swarm orchestration discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "CoFlyers"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/micros-uav/CoFlyers"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "General platform for evaluating cooperative motion algorithms of drone swarms."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["cooperative_motion", "swarm_evaluation", "algorithm_benchmarking"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local CoFlyers runtime artifacts without external service calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if any(
            self._env(key) and Path(self._env(key)).expanduser().exists()  # noqa: PTH110
            for key in self._ENV_PATH_KEYS
        ):
            return True

        if any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper operation and use deterministic fixture replay offline."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical policy: replay fixture when forward links are disconnected.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "available": True,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "request": request,
                "error": "CoFlyers runtime is not installed or configured on this node.",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request,
            "message": "CoFlyers dependencies validated for local cooperative swarm evaluation.",
        }
