"""Incident response plan template integration adapter.

Military/tactical context:
The adapter provides offline plan templates so command staff can execute cyber
incident battle drills under degraded communications conditions.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class IncidentResponsePlanTemplateAdapter(IntegrationAdapter):
    """Wrap incident-response templates with deterministic tactical fallback."""

    integration_id = "incident-response-plan-template"
    domain = "cyber"
    _SUPPORTED_OPERATIONS = {"list_templates", "generate_checklist", "review_playbook"}

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
            name=str(raw.get("name") or "incident-response-plan-template"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description="Incident response template adapter for tactical cyber battle drills.",
            integration_type="adapter",
            capabilities=["ir-planning", "checklist-generation", "playbook-governance"],
            system_dependencies=["pandoc"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        template_path = self._env("INCIDENT_RESPONSE_TEMPLATE_PATH")
        local_templates_exist = bool(template_path) and Path(template_path).exists()
        return local_templates_exist or bool(shutil.which("pandoc"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute template retrieval with strict, sovereign-safe behavior."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "generate_checklist")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture-based incident response template package.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "result": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "source": "runtime",
            "available": self.validate_availability(),
            "result": {
                "status": "simulated",
                "detail": "Template rendering is simulated; no network or SaaS dependency is invoked.",
            },
        }
