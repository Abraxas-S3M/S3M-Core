"""Adapter for DataScienceInteractivePython dashboard workflows.

Military/tactical context:
This wrapper allows analysts to run interactive data-science dashboard drills
for training simulations on sovereign, disconnected compute nodes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class DatascienceinteractivepythonAdapter(IntegrationAdapter):
    """Integration adapter for DataScienceInteractivePython dashboards."""

    integration_id = "datascienceinteractivepython"
    domain = "dashboard"

    _manifest_path = Path(__file__).resolve().parent / "manifest.yaml"
    _tool_modules = ("panel", "bokeh", "dash")
    _tool_commands = ("panel", "bokeh", "dash")

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("DataScienceInteractivePython manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        manifest = self._load_manifest()
        return IntegrationManifest(
            name=str(manifest.get("name") or "DataScienceInteractivePython"),
            slug=str(manifest.get("slug") or self.integration_id),
            domain=str(manifest.get("domain") or self.domain),
            source_url=str(manifest.get("source_url") or ""),
            license=str(manifest.get("license") or "MIT"),
            description=str(
                manifest.get("description")
                or "Interactive dashboards for data-science training simulations."
            ),
            integration_type="adapter",
            capabilities=["interactive_dashboard", "simulation_training", "data_exploration"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            available = bool(self._read_fixture("sample_response.json"))
            self.logger.debug("Airgapped availability=%s for %s", available, self.integration_id)
            return available

        module_available = any(importlib.util.find_spec(name) is not None for name in self._tool_modules)
        command_available = any(shutil.which(command) is not None for command in self._tool_commands)
        available = module_available or command_available
        self.logger.debug("Online availability=%s for %s", available, self.integration_id)
        return available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request = params or {}
        operation = str(request.get("operation") or "render_training_dashboard")

        if self.is_airgapped:
            self.logger.info("Serving %s fixture for offline simulation drill", self.integration_id)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "data": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            self.logger.warning("DataScienceInteractivePython toolchain unavailable")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "message": "Interactive dashboard dependencies are not installed.",
            }

        self.logger.info("Prepared dashboard operation '%s' for analyst workflow", operation)
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": request,
            "message": "Dashboard execution wrapper is ready for orchestrator handoff.",
        }

