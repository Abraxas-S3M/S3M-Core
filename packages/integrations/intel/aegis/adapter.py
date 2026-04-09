"""AEGIS adapter for S3M intelligence and early-warning briefings.

Military/tactical context:
This wrapper standardizes early-warning and geostrategic indicators for command
decision support when sovereign operators must function without cloud services.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AegisAdapter(IntegrationAdapter):
    """Thin adapter for AEGIS early-warning intelligence workflows."""

    integration_id = "aegis"
    domain = "intel"
    _SUPPORTED_OPERATIONS = {
        "early_warning_scan",
        "geostrategic_assessment",
        "briefing_summary",
    }
    _TOOL_MODULES = ("aegis",)
    _TOOL_COMMANDS = ("aegis",)

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "AEGIS"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=(
                "Early-warning and geostrategic intelligence adapter for "
                "commander decision support in sovereign operations."
            ),
            integration_type="adapter",
            capabilities=["early-warning", "geostrategic-analysis", "briefing-support"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Validate local AEGIS tooling before runtime execution."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        module_available = any(importlib.util.find_spec(name) is not None for name in self._TOOL_MODULES)
        command_available = any(shutil.which(command) is not None for command in self._TOOL_COMMANDS)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute supported workflows or return fixture data while airgapped."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation") or "briefing_summary").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning AEGIS fixture for offline early-warning briefing.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": request,
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
                "request": request,
                "message": "AEGIS tooling is not available on this host.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": request,
            "message": "Runtime handoff prepared; live execution is environment-specific.",
        }

