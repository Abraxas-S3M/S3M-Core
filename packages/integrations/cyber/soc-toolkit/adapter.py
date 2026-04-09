"""Adapter for soc-toolkit open-source SOC workflows.

Military/tactical context:
This wrapper allows S3M cyber teams to consume SOC-toolkit readiness and
incident-response context in a controlled format suitable for sovereign,
airgapped defense enclaves.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SocToolkitAdapter(IntegrationAdapter):
    """Integration wrapper for the soc-toolkit repository."""

    integration_id = "soc-toolkit"
    domain = "cyber"
    _ALLOWED_ACTIONS = frozenset({"status", "collect", "triage", "enrich"})
    _TOOL_CANDIDATES = ("docker", "wazuh-manager", "thehive", "misp")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}
        return IntegrationManifest(
            name=str(raw.get("name") or "soc-toolkit"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Open-source SOC toolkit adapter for containerized detection and response tooling."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        if self.is_airgapped:
            return fixture_ready
        if self._env("SOC_TOOLKIT_HOME") or self._env("DOCKER_HOST"):
            return True
        return any(shutil.which(tool) for tool in self._TOOL_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "data": self._read_fixture("sample_response.json"),
            }

        action = str(params.get("action", "status")).strip().lower()
        if action not in self._ALLOWED_ACTIONS:
            return {
                "ok": False,
                "error": "invalid_action",
                "allowed_actions": sorted(self._ALLOWED_ACTIONS),
            }

        mission_cell = str(params.get("mission_cell", "soc-toolkit-cell")).strip()
        # Tactical hardening: mission cell labels must stay shell-safe.
        if not mission_cell or len(mission_cell) > 128 or any(
            char in mission_cell for char in (";", "|", "&", "`", "$", "\n", "\r")
        ):
            return {"ok": False, "error": "invalid_mission_cell"}

        available = self.validate_availability()
        return {
            "ok": available,
            "integration_id": self.integration_id,
            "mode": self.mode,
            "action": action,
            "mission_cell": mission_cell,
            "available": available,
            "status": "ready" if available else "unavailable",
        }
