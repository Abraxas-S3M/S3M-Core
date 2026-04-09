"""Adapter for Assume mission-market simulation dashboards.

Military/tactical context:
This wrapper lets S3M planners expose ASSUME scenario outputs through a
standard adapter surface so command staff can rehearse resource and market
stress scenarios on isolated infrastructure.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AssumeAdapter(IntegrationAdapter):
    """Integration adapter for the Assume dashboard toolkit."""

    integration_id = "assume"
    domain = "dashboard"

    _manifest_path = Path(__file__).resolve().parent / "manifest.yaml"
    _tool_modules = ("assume",)
    _tool_commands = ("assume",)

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Assume manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        manifest = self._load_manifest()
        return IntegrationManifest(
            name=str(manifest.get("name") or "Assume"),
            slug=str(manifest.get("slug") or self.integration_id),
            domain=str(manifest.get("domain") or self.domain),
            source_url=str(manifest.get("source_url") or ""),
            license=str(manifest.get("license") or "MIT"),
            description=str(
                manifest.get("description")
                or "Agent-based dashboard for market and tactical training simulation."
            ),
            integration_type="adapter",
            capabilities=["agent_simulation", "scenario_dashboard", "training_rehearsal"],
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
        operation = str(request.get("operation") or "run_scenario")

        if self.is_airgapped:
            self.logger.info("Serving %s fixture for tactical rehearsal", self.integration_id)
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
            self.logger.warning("Assume toolchain unavailable for online execution")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "message": "Assume package or command is not available in this environment.",
            }

        self.logger.info("Prepared Assume operation '%s' for mission staff workflow", operation)
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": request,
            "message": "Assume execution wrapper is ready for local orchestrator handoff.",
        }

