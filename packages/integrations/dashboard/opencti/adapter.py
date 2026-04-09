"""OpenCTI adapter for tactical cyber-threat dashboard operations.

Military/tactical context:
This wrapper provides a controlled interface so command-center operators can
inspect cyber risk posture through a sovereign S3M dashboard pipeline without
requiring live internet connectivity during contested operations.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenctiAdapter(IntegrationAdapter):
    """S3M dashboard integration for OpenCTI telemetry surfaces."""

    integration_id = "opencti"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter manifest metadata from package-local YAML."""

        raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name", "OpenCTI")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/OpenCTI-Platform/opencti")),
            license=str(raw.get("license", "Apache 2.0")),
            description=str(
                raw.get(
                    "description",
                    "Cyber threat intelligence dashboard for observables, campaigns, and mission risk scoring.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(raw.get("capabilities", ["threat_dashboard", "risk_monitoring", "observable_overview"])),
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Confirm local availability of OpenCTI tooling or offline fixture."""

        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("pycti") is not None or shutil.which("opencti") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return mission-relevant OpenCTI dashboard telemetry."""

        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a mapping when provided")

        safe_params = dict(params or {})
        action = str(safe_params.get("action", "dashboard_summary")).strip().lower()
        if action not in {"dashboard_summary", "threat_overview", "risk_snapshot"}:
            raise ValueError("Unsupported action for opencti adapter")

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
                "tooling": "pycti/opencti",
            },
        }

