"""World Monitor integration adapter.

Military/tactical context:
This adapter stages geopolitical risk snapshots so command dashboards can
retain strategic situational awareness when disconnected from external feeds.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WorldMonitorAdapter(IntegrationAdapter):
    """Adapter wrapper for the World Monitor open-source dashboard."""

    integration_id = "world-monitor"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.dashboard.world-monitor")

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_dict(self) -> dict[str, Any]:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter metadata used for tactical integration discovery."""
        raw = self._manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "World Monitor"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/koala73/worldmonitor"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Geopolitical dashboard for risks, conflicts, and forecasts."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities")),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Verify local runtime support before dashboard execution attempts."""
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        command_ready = any(
            shutil.which(command) for command in ("worldmonitor", "streamlit", "python3")
        )
        return fixture_ready if self.is_airgapped else command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute dashboard wrapper with secure airgapped fixture fallback."""
        safe_params = params or {}
        operation = str(safe_params.get("operation") or "overview")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "data": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "error": "World Monitor runtime is not available on this node.",
            }

        # External calls are intentionally disabled for sovereign offline posture.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "message": "Local runtime validated; remote dashboard invocation is disabled by policy.",
        }
