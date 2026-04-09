"""spot_bt_ros integration adapter.

Military/tactical context:
This adapter verifies behavior-tree control readiness for Spot UGV missions,
allowing local orchestration to continue in communications-denied operations.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SpotBtRosAdapter(IntegrationAdapter):
    """Wrap spot_bt_ros package checks and execution responses."""

    integration_id = "spot-bt-ros"
    domain = "autonomy"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.autonomy.spot-bt-ros")
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        raw: dict[str, Any] = {}
        if self._manifest_path.exists():
            raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}

        return IntegrationManifest(
            name=str(raw.get("name") or "spot_bt_ros"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Behavior-tree control integration for Boston Dynamics Spot ROS2 operations."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["spot_behavior_tree_control", "ros2_robot_mission_execution"]
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["ros2"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        ros2_bin = shutil.which("ros2")
        if not ros2_bin:
            return False

        try:
            probe = subprocess.run(
                [ros2_bin, "pkg", "prefix", "spot_bt_ros"],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return probe.returncode == 0

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request = params or {}
        if self.is_airgapped:
            payload = self._read_fixture("sample_response.json")
            payload["execution_mode"] = "airgapped"
            payload["requested_action"] = str(request.get("action", "dispatch_spot_mission"))
            return payload

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "detail": "spot_bt_ros package is not reachable from this node.",
                "fallback": self._read_fixture("sample_response.json"),
            }

        ros2_bin = shutil.which("ros2")
        install_prefix = ""
        if ros2_bin:
            probe = subprocess.run(
                [ros2_bin, "pkg", "prefix", "spot_bt_ros"],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
            if probe.returncode == 0:
                install_prefix = probe.stdout.strip()

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": str(request.get("action", "dispatch_spot_mission")),
            "install_prefix": install_prefix,
            "tactical_note": "Spot behavior-tree controller is available for dismounted recon tasking.",
        }
