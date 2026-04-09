"""Adapter for wazuh-soc-enterprise defensive SOC orchestration.

Military/tactical context:
This wrapper standardizes enterprise SOC telemetry access for mission defense
cells, enabling offline-ready situational awareness and repeatable triage
actions on sovereign infrastructure.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WazuhSocEnterpriseAdapter(IntegrationAdapter):
    """Integration wrapper for the wazuh-soc-enterprise repository."""

    integration_id = "wazuh-soc-enterprise"
    domain = "cyber"
    _ALLOWED_ACTIONS = frozenset({"status", "collect", "triage", "investigate"})
    _TOOL_CANDIDATES = ("wazuh-manager", "suricata", "caldera", "docker")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}
        return IntegrationManifest(
            name=str(raw.get("name") or "wazuh-soc-enterprise"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Enterprise SOC adapter spanning Wazuh, DFIR workflows, and SOAR automations."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        if self.is_airgapped:
            return fixture_ready
        if self._env("WAZUH_HOME") or self._env("CALDERA_HOME"):
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

        scope = str(params.get("scope", "enterprise-soc")).strip()
        # Tactical hardening: block command-like control symbols in user input.
        if not scope or len(scope) > 128 or any(char in scope for char in (";", "|", "&", "`", "$", "\n", "\r")):
            return {"ok": False, "error": "invalid_scope"}

        available = self.validate_availability()
        return {
            "ok": available,
            "integration_id": self.integration_id,
            "mode": self.mode,
            "action": action,
            "scope": scope,
            "available": available,
            "status": "ready" if available else "unavailable",
        }
