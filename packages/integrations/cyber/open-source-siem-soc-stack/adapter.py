"""Adapter for Open-Source-SIEM_SOC-Stack.

Military/tactical context:
This wrapper provides a sovereign interface for SOC telemetry from containerized
SIEM components, helping tactical cyber teams preserve monitoring continuity in
offline and contested operating environments.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenSourceSiemSocAdapter(IntegrationAdapter):
    """Integration wrapper for Open-Source-SIEM_SOC-Stack."""

    integration_id = "open-source-siem-soc-stack"
    domain = "cyber"
    _ALLOWED_ACTIONS = frozenset({"status", "collect", "dashboard", "orchestrate"})
    _TOOL_CANDIDATES = ("docker", "docker-compose", "wazuh-manager", "graylog")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}
        return IntegrationManifest(
            name=str(raw.get("name") or "Open-Source-SIEM_SOC-Stack"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Dockerized SOC stack adapter for Wazuh, Graylog, Grafana, and Shuffle SOAR."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        if self.is_airgapped:
            return fixture_ready
        if self._env("DOCKER_HOST"):
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

        enclave = str(params.get("enclave", "soc-stack")).strip()
        # Tactical hardening: deny control characters in enclave identifiers.
        if not enclave or len(enclave) > 128 or any(char in enclave for char in (";", "|", "&", "`", "$", "\n", "\r")):
            return {"ok": False, "error": "invalid_enclave"}

        available = self.validate_availability()
        return {
            "ok": available,
            "integration_id": self.integration_id,
            "mode": self.mode,
            "action": action,
            "enclave": enclave,
            "available": available,
            "status": "ready" if available else "unavailable",
        }
