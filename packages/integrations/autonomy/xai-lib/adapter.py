"""XAI-Lib adapter for unified explanation methods.

Military/tactical context:
Multiple explainers must be compared quickly to verify autonomous model
decisions under mission constraints. This adapter provides a stable, offline
interface for that validation process.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class XaiLibAdapter(IntegrationAdapter):
    """Adapter for orchestrating XAI-Lib explanation workflows."""

    integration_id = "xai-lib"
    domain = "autonomy"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load and return metadata for registry and mission planners."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "XAI-Lib"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/kdd-lab/XAI-Lib"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Unified Python library for various XAI explanation methods."
            ),
            integration_type="adapter",
            capabilities=[
                "multi_method_explanations",
                "counterfactual_analysis",
                "mission_model_transparency",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Determine if local XAI-Lib modules are present."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        module_candidates = ("xailib", "xai_lib")
        return any(importlib.util.find_spec(name) is not None for name in module_candidates)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute explanation workflow or fallback to deterministic fixture."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "compare_explainers")),
                    "explainer_family": str(params.get("explainer_family", "shap_lime_anchor")),
                }
                return fixture
            return {"status": "error", "reason": "fixture_not_found", "integration_id": self.integration_id}

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "reason": "xai_lib_not_installed",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local XAI-Lib detected; invoke trusted local runner for live explanation jobs.",
        }
