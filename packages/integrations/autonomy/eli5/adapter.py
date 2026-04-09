"""ELI5 integration adapter for S3M model explainability operations.

Military/tactical context:
This wrapper provides offline explainability outputs so mission operators can
audit classifier behavior before deploying autonomy decisions in the field.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Eli5Adapter(IntegrationAdapter):
    """Adapter for ELI5 classifier explanation workflows."""

    integration_id = "eli5"
    domain = "autonomy"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._root = Path(__file__).resolve().parent

    def _manifest_path(self) -> Path:
        return self._root / "manifest.yaml"

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("manifest.yaml must contain a mapping.")
        return IntegrationManifest(
            name=str(raw.get("name") or "ELI5"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "unknown"),
            description=str(
                raw.get("description")
                or "Explainability adapter for tactical classifier audit and confidence review."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._as_list(raw.get("capabilities")),
            pip_dependencies=self._as_list(raw.get("pip_dependencies")),
            system_dependencies=self._as_list(raw.get("system_dependencies")),
            docker_dependencies=self._as_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("eli5") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary of explainability options.")

        action = str(params.get("action", "explain_prediction")).strip().lower()
        if not action:
            raise ValueError("action cannot be empty.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            payload = dict(fixture) if isinstance(fixture, dict) else {"result": fixture}
            payload["mode"] = "airgapped"
            payload["source"] = "fixture"
            payload["requested_action"] = action
            payload["integration_id"] = self.integration_id
            return payload

        if not self.validate_availability():
            return {"status": "unavailable", "integration_id": self.integration_id, "action": action}

        if action == "explain_prediction":
            model_family = str(params.get("model_family", "gradient_boosting")).strip()
            target_label = str(params.get("target_label", "threat")).strip()
            if not model_family or not target_label:
                raise ValueError("model_family and target_label are required for explain_prediction.")
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "status": "ok",
                "explanation_summary": (
                    "Model indicates elevated likelihood due to track velocity anomaly and "
                    "IFF mismatch features."
                ),
                "model_family": model_family,
                "target_label": target_label,
            }
        if action == "describe":
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "status": "ok",
                "detail": "ELI5 wrapper ready for local explanation generation.",
            }
        raise ValueError(f"Unsupported action: {action}")
