"""Panopticon AI adapter for web-based tactical wargaming dashboards."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PanopticonAiAdapter(IntegrationAdapter):
    """Wraps Panopticon AI for force-projection visualization in command dashboards."""

    integration_id = "panopticon-ai"
    domain = "dashboard"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Panopticon AI manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for tactical dashboard discovery."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Panopticon AI"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/Panopticon-AI-team/panopticon"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Web-based military simulation dashboard for wargaming projection and command review."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities") or ["projection_panels", "force_projection"]],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Confirm local Panopticon AI runtime availability."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("PANOPTICON_AI_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(shutil.which(command) for command in ("panopticon", "panopticon-ai"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute dashboard projection retrieval, returning fixture output offline."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("Panopticon AI execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing Panopticon AI fixture: sample_response.json")
            response = dict(fixture)
            response["mode"] = "airgapped"
            response["request"] = request
            return response

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "detail": "Panopticon AI CLI or local checkout path was not found.",
            }

        # Tactical safety: online mode avoids uncontrolled external requests.
        return {
            "status": "deferred",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "request": request,
            "detail": "Local Panopticon AI execution is available but intentionally stubbed.",
        }

