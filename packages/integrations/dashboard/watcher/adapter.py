"""Watcher adapter for AI-assisted threat-hunting dashboards."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WatcherAdapter(IntegrationAdapter):
    """Wraps Watcher for tactical anomaly detection and intel triage dashboards."""

    integration_id = "watcher"
    domain = "dashboard"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Watcher manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for dashboard-level threat hunting orchestration."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Watcher"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/thalesgroup-cert/Watcher"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "AI-powered threat hunting dashboard for anomaly surfacing and analyst triage."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities") or ["threat_hunting", "anomaly_review"]],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Confirm local Watcher runtime availability while remaining offline-safe."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("WATCHER_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(shutil.which(command) for command in ("watcher", "watcher-cli"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute threat dashboard retrieval with fixture replay in disconnected mode."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("Watcher execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing Watcher fixture: sample_response.json")
            response = dict(fixture)
            response["mode"] = "airgapped"
            response["request"] = request
            return response

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "detail": "Watcher CLI or local checkout path was not found.",
            }

        # Tactical containment: online behavior is deferred to explicit local wiring.
        return {
            "status": "deferred",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "request": request,
            "detail": "Local Watcher execution is available but intentionally stubbed.",
        }

