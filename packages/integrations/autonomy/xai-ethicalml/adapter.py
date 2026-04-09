"""xai (EthicalML) integration adapter.

Military/tactical context:
This adapter enables local explainability summaries for mission ML outputs so
operators can audit model rationale during contested or disconnected operations.
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class XaiethicalmlAdapter(IntegrationAdapter):
    """Wrap EthicalML XAI toolbox availability and execution responses."""

    integration_id = "xai-ethicalml"
    domain = "autonomy"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.autonomy.xai-ethicalml")
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        raw: dict[str, Any] = {}
        if self._manifest_path.exists():
            raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}

        return IntegrationManifest(
            name=str(raw.get("name") or "xai (EthicalML)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Responsible-ML explainability support for tactical edge model audits."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["feature_attribution", "responsible_ml_checks", "explainability_reporting"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["xai"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        module_present = importlib.util.find_spec("xai") is not None
        python_present = shutil.which("python3") is not None or shutil.which("python") is not None
        return module_present and python_present

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request = params or {}
        if self.is_airgapped:
            payload = self._read_fixture("sample_response.json")
            payload["execution_mode"] = "airgapped"
            payload["requested_action"] = str(request.get("action", "generate_explanation"))
            return payload

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "detail": "EthicalML xai package is not installed in this Python runtime.",
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": str(request.get("action", "generate_explanation")),
            "explanation_scope": str(request.get("scope", "model_output")),
            "tactical_note": "Explainability module is available for operator trust and audit briefings.",
        }
