"""alibi integration adapter for S3M model-inspection workflows.

Military/tactical context:
This adapter exposes black-box inspection and counterfactual explanations so
operators can challenge model outputs prior to high-consequence actions.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AlibiAdapter(IntegrationAdapter):
    """Adapter for alibi black-box inspection and counterfactual analysis."""

    integration_id = "alibi"
    domain = "hmi"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.hmi.alibi")
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
        """Load alibi manifest metadata for S3M integration discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "alibi"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Black-box model inspection and counterfactual reasoning for tactical AI systems."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["counterfactual_explanations", "anchor_explanations", "drift_monitoring"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["alibi"]),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check for local alibi availability without external service usage."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if importlib.util.find_spec("alibi") is not None:
            return True

        configured_path = self._env("ALIBI_PATH")
        return bool(configured_path and Path(configured_path).exists())

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run model-inspection wrapper flow with deterministic fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of inspection options.")

        action = str(request_params.get("action", "counterfactual")).strip().lower()
        if not action:
            raise ValueError("action cannot be empty.")

        if self.is_airgapped:
            # Tactical requirement: preserve repeatable outputs for offline mission review boards.
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
                "error": "alibi package is not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
                "requested_action": action,
            }

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": action,
            "inspection_mode": str(request_params.get("inspection_mode", "counterfactual")),
            "detail": "alibi wrapper ready for local model-inspection and explanation tasks.",
        }
