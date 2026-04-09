"""OmniXAI integration adapter for S3M HMI explanation workflows.

Military/tactical context:
This adapter enables multimodal AI explanation summaries so mission crews can
cross-check autonomous recommendations before command approval.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OmnixaiAdapter(IntegrationAdapter):
    """Adapter for OmniXAI multimodal explainability functions."""

    integration_id = "omnixai"
    domain = "hmi"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.hmi.omnixai")
        self._root = Path(__file__).resolve().parent

    def _manifest_path(self) -> Path:
        return self._root / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _load_manifest_dict(self) -> dict[str, Any]:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("manifest.yaml must contain a YAML mapping.")
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for registry and orchestration flows."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "OmniXAI"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "BSD-3-Clause"),
            description=str(
                raw.get("description")
                or "Omni-way explainable AI for multimodal tactical model interrogation."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["tabular_explanations", "vision_explanations", "nlp_explanations"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["omnixai"]),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether OmniXAI is importable in the local runtime."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if importlib.util.find_spec("omnixai") is not None:
            return True

        configured_path = self._env("OMNIXAI_PATH")
        return bool(configured_path and Path(configured_path).exists())

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run explanation orchestration with deterministic airgapped fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of explanation controls.")

        action = str(request_params.get("action", "multimodal_explanation")).strip().lower()
        if not action:
            raise ValueError("action cannot be empty.")

        if self.is_airgapped:
            # Tactical requirement: preserve deterministic outputs for offline briefing.
            fixture_payload = self._read_fixture("sample_response.json")
            payload = dict(fixture_payload) if isinstance(fixture_payload, dict) else {"result": fixture_payload}
            payload.update(
                {
                    "integration_id": self.integration_id,
                    "domain": self.domain,
                    "mode": "airgapped",
                    "source": "fixture",
                    "requested_action": action,
                }
            )
            payload.setdefault("status", "ok")
            return payload

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "error": "omnixai package is not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
                "requested_action": action,
            }

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": action,
            "modalities": request_params.get("modalities", ["vision", "text"]),
            "detail": "OmniXAI wrapper ready for multimodal mission explanation workflows.",
        }
