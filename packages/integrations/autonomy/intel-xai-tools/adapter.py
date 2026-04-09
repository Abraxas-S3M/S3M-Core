"""Intel XAI Tools adapter for mission-model explainability.

Military/tactical context:
Commanders need transparent AI outputs to verify model behavior before
deployment in contested environments. This wrapper standardizes Intel XAI
tooling behind an airgapped-safe S3M interface.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class IntelXaiToolsAdapter(IntegrationAdapter):
    """Adapter for Intel-specific explainability and fairness workflows."""

    integration_id = "intel-xai-tools"
    domain = "autonomy"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata used by mission orchestration."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "intel-xai-tools"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/intel/intel-xai-tools"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Intel-specific XAI tooling for model interpretability and fairness."
            ),
            integration_type="adapter",
            capabilities=[
                "model_explainability",
                "fairness_assessment",
                "tactical_model_validation",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check local module availability without external network access."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        module_candidates = ("intel_xai_tools", "intelxaitools")
        return any(importlib.util.find_spec(name) is not None for name in module_candidates)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run explainability workflow, using fixture output in offline mode."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "explain_model")),
                    "model_id": str(params.get("model_id", "mission-detector-v1")),
                }
                return fixture
            return {"status": "error", "reason": "fixture_not_found", "integration_id": self.integration_id}

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "reason": "intel_xai_tools_not_installed",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local Intel XAI tooling detected; invoke local runtime pipeline for live runs.",
        }
