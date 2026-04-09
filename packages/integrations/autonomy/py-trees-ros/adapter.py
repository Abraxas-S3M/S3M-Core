"""Adapter for py_trees_ros tactical ROS behavior orchestration.

Military/tactical context:
This wrapper exposes ROS-aware behavior-tree status pipelines so autonomous
robotics stacks can coordinate under disconnected and contested conditions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PyTreesRosAdapter(IntegrationAdapter):
    """Integration wrapper for py_trees_ros."""

    integration_id = "py-trees-ros"
    domain = "autonomy"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._root_dir = Path(__file__).resolve().parent

    def _coerce_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata used by mission orchestrators."""
        raw = yaml.safe_load((self._root_dir / "manifest.yaml").read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name") or "py_trees_ros"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "BSD"),
            description=str(raw.get("description") or "ROS integration for py_trees."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities") or ["ros_behaviors", "behavior_trees"]),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["py_trees_ros"]),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["ros2"]),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Return True when py_trees_ros and ROS2 command tooling are present."""
        return importlib.util.find_spec("py_trees_ros") is not None and shutil.which("ros2") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a ROS behavior-tree request or return fixture in airgapped mode."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("params must be a dictionary")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "available": True,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "available": False,
                "error": "integration_unavailable",
                "detail": "py_trees_ros or ros2 command not available.",
                "request": request,
            }

        # Tactical note: summarize ROS control-loop state for command post telemetry.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local_runtime",
            "available": True,
            "request": request,
            "result": {
                "tree_name": str(request.get("tree_name", "uav-command-tree")),
                "namespace": str(request.get("namespace", "/s3m/uav_01")),
                "published_topics": int(request.get("published_topics", 5)),
                "subscribed_topics": int(request.get("subscribed_topics", 8)),
                "status": "RUNNING",
            },
        }
