"""XAI-Cybersecurity adapter for defensive autonomy analytics.

Military/tactical context:
Autonomous cyber defense requires explainable intrusion detections so analysts
can rapidly justify containment actions on sovereign military networks.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class XaiCybersecurityAdapter(IntegrationAdapter):
    """Adapter for explainable cybersecurity inference workflows."""

    integration_id = "xai-cybersecurity"
    domain = "autonomy"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata consumed by S3M orchestration."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "XAI-Cybersecurity"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/ivoafonsobispo/XAI-Cybersecurity"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "XAI for intrusion detection and cybersecurity analytics."
            ),
            integration_type="adapter",
            capabilities=[
                "intrusion_explanation",
                "cyber_anomaly_justification",
                "tactical_network_defense",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check whether local XAI cybersecurity modules are available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        module_candidates = ("xai_cybersecurity", "xaicybersecurity")
        return any(importlib.util.find_spec(name) is not None for name in module_candidates)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run cybersecurity explanation pipeline with offline fallback."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "explain_intrusion_alert")),
                    "alert_id": str(params.get("alert_id", "soc-alert-001")),
                }
                return fixture
            return {"status": "error", "reason": "fixture_not_found", "integration_id": self.integration_id}

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "reason": "xai_cybersecurity_not_installed",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local XAI-Cybersecurity tooling detected; execute via trusted SOC runtime.",
        }
