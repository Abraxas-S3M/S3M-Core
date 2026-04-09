"""Phoenix adapter for tactical AI-observability dashboard operations.

Military/tactical context:
This wrapper feeds sovereign command dashboards with local tracing and eval
summaries so teams can verify LLM mission-support behavior under constrained or
airgapped operating conditions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PhoenixAdapter(IntegrationAdapter):
    """S3M dashboard integration for Phoenix trace intelligence."""

    integration_id = "phoenix"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter metadata from manifest.yaml."""

        raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name", "Phoenix")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/Arize-ai/phoenix")),
            license=str(raw.get("license", "Apache 2.0")),
            description=str(
                raw.get(
                    "description",
                    "AI observability tracing dashboard for LLM experiments, prompts, and evaluation signals.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(raw.get("capabilities", ["trace_dashboard", "llm_experiment_monitoring", "evaluation_triage"])),
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check if Phoenix tooling is locally available."""

        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("phoenix") is not None or shutil.which("phoenix") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return dashboard-friendly Phoenix observability snapshots."""

        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a mapping when provided")

        safe_params = dict(params or {})
        action = str(safe_params.get("action", "dashboard_summary")).strip().lower()
        if action not in {"dashboard_summary", "trace_health", "experiment_rollup"}:
            raise ValueError("Unsupported action for phoenix adapter")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            self.logger.info("Returning airgapped fixture payload for action=%s", action)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "action": action,
                "result": fixture,
            }

        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local_probe",
            "action": action,
            "available": available,
            "result": {
                "status": "ready" if available else "unavailable",
                "tooling": "phoenix",
            },
        }

