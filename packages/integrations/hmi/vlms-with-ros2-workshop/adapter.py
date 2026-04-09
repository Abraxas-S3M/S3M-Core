"""Adapter for vlms_with_ros2_workshop.

Military/tactical context:
This wrapper supports offline rehearsals of multimodal robot perception loops
so Human-Machine Teaming operators can validate ROS2 VLM workflows before
field deployment on disconnected mission networks.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class VlmsWithRos2WorkshopAdapter(IntegrationAdapter):
    """S3M integration adapter for vlms_with_ros2_workshop."""

    integration_id = "vlms-with-ros2-workshop"
    domain = "hmi"
    _COMMAND_CANDIDATES = ("ros2", "colcon", "python3", "openvino_info")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _as_list(value: Any) -> list[str]:
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
            self.logger.exception("Manifest parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest must be a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata from local manifest.yaml."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "vlms_with_ros2_workshop")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Workshop utilities for ROS2 Vision-Language Model integration and operator-guided perception.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._as_list(
                raw.get("capabilities", ["vlm_perception", "ros2_pipeline_validation", "edge_inference_rehearsal"])
            ),
            pip_dependencies=self._as_list(raw.get("pip_dependencies")),
            system_dependencies=self._as_list(raw.get("system_dependencies")),
            docker_dependencies=self._as_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path", "")),
        )

    def validate_availability(self) -> bool:
        """Check whether local ROS2/VLM tooling is available without network calls."""
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

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run tactical VLM/ROS2 wrapper flow with deterministic fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of tactical HMI options.")

        operation = str(request_params.get("operation", "run_vlm_inference")).strip().lower()
        if not operation:
            raise ValueError("operation cannot be empty.")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving fixture data for ROS2 VLM rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
                "request": request_params,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "vlms_with_ros2_workshop tooling is not installed or configured",
                "request": request_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local ROS2 VLM prerequisites validated; mission controllers can invoke live pipelines.",
        }
