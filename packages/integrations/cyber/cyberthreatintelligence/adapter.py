"""Adapter for CyberThreatIntelligence SOC intelligence resources.

Military/tactical context:
This adapter gives analysts in constrained or denied networks a consistent
way to retrieve cyber threat picture snapshots for defensive planning.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class CyberthreatintelligenceAdapter(IntegrationAdapter):
    """Wrap CyberThreatIntelligence content for SOC workflows."""

    integration_id = "cyberthreatintelligence"
    domain = "cyber"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata from local manifest YAML."""
        raw_manifest = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("CyberThreatIntelligence manifest must be a mapping.")

        return IntegrationManifest(
            name=str(raw_manifest.get("name") or "CyberThreatIntelligence"),
            slug=str(raw_manifest.get("slug") or self.integration_id),
            domain=str(raw_manifest.get("domain") or self.domain),
            source_url=str(raw_manifest.get("source_url") or ""),
            license=str(raw_manifest.get("license") or "Unknown"),
            description=str(
                raw_manifest.get("description")
                or "SOC-oriented cyber threat dashboard resources for defensive operations."
            ),
            integration_type=str(raw_manifest.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw_manifest.get("capabilities", [])],
            pip_dependencies=[str(item) for item in raw_manifest.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw_manifest.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw_manifest.get("docker_dependencies", [])],
            airgapped_support=bool(raw_manifest.get("airgapped_support", True)),
            vendor_path=str(raw_manifest.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if local resources are present without external API calls."""
        fixture_path = self._fixture_dir / "sample_response.json"
        if self.is_airgapped:
            return fixture_path.exists()

        configured_path = Path(
            self._env("CYBERTHREATINTELLIGENCE_PATH", str(Path.cwd() / "vendors" / self.integration_id))
        )
        known_binary = shutil.which("cyberthreatintelligence")
        return configured_path.exists() or known_binary is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return CTI snapshot data for tactical SOC triage tasks."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided.")

        safe_params = params or {}
        requested_view = str(safe_params.get("view", "dashboard"))
        max_items = int(safe_params.get("limit", 25))

        if max_items < 1 or max_items > 500:
            raise ValueError("limit must be between 1 and 500 for controlled SOC output volume.")

        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            if not isinstance(fixture_payload, dict):
                raise ValueError("sample_response.json fixture must contain a JSON object.")

            indicators = fixture_payload.get("priority_indicators", [])
            if isinstance(indicators, list):
                fixture_payload["priority_indicators"] = indicators[:max_items]
            fixture_payload["mode"] = "airgapped"
            fixture_payload["requested_view"] = requested_view
            return fixture_payload

        if not self.validate_availability():
            raise RuntimeError(
                "CyberThreatIntelligence resources are not available locally; "
                "set CYBERTHREATINTELLIGENCE_PATH or enable airgapped mode."
            )

        # Tactical note: online mode still avoids external calls for sovereign/offline safety.
        return {
            "integration": self.integration_id,
            "mode": "online",
            "status": "available",
            "requested_view": requested_view,
            "limit": max_items,
            "data_source": "local_installation",
            "message": "Local CyberThreatIntelligence resources are reachable for SOC operations.",
        }

