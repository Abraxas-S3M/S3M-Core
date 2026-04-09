"""Adapter for Enterprise-SOC-Detection-and-Response-Wazuh.

Military/tactical context:
The wrapper maps Wazuh-driven ATT&CK detections into a standardized S3M
interface so frontline cyber operators can triage hostile activity even when
operating in isolated tactical enclaves.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class EnterpriseSocDetectionAndAdapter(IntegrationAdapter):
    """Integration wrapper for Enterprise-SOC-Detection-and-Response-Wazuh."""

    integration_id = "enterprise-soc-detection-and-response-wa"
    domain = "cyber"
    _ALLOWED_ACTIONS = frozenset({"status", "triage", "investigate", "report"})
    _TOOL_CANDIDATES = ("wazuh-manager", "wazuh-dashboard", "docker")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}
        return IntegrationManifest(
            name=str(raw.get("name") or "Enterprise-SOC-Detection-and-Response-Wazuh"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Enterprise Wazuh SOC adapter with ATT&CK-aligned detection and response workflows."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        if self.is_airgapped:
            return fixture_ready
        if self._env("WAZUH_HOME"):
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

        operation_focus = str(params.get("operation_focus", "enterprise-soc-ops")).strip()
        # Tactical hardening: sanitize operator-provided mission focus selectors.
        if not operation_focus or len(operation_focus) > 128 or any(
            char in operation_focus for char in (";", "|", "&", "`", "$", "\n", "\r")
        ):
            return {"ok": False, "error": "invalid_operation_focus"}

        available = self.validate_availability()
        return {
            "ok": available,
            "integration_id": self.integration_id,
            "mode": self.mode,
            "action": action,
            "operation_focus": operation_focus,
            "available": available,
            "status": "ready" if available else "unavailable",
        }
