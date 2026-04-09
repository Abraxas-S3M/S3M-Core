"""Quantus integration adapter for S3M explanation-quality assessment.

Military/tactical context:
This wrapper validates explanation robustness so mission teams can detect
fragile AI rationale before autonomous assets are trusted in operations.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class QuantusAdapter(IntegrationAdapter):
    """Adapter for Quantus explanation quality and robustness metrics."""

    integration_id = "quantus"
    domain = "hmi"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.hmi.quantus")
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
        """Return integration metadata for S3M registry and orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Quantus"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Toolkit for evaluating explanation quality and robustness in neural systems."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["faithfulness_metrics", "robustness_metrics", "complexity_metrics"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["quantus"]),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if Quantus is available locally for explanation evaluation."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if importlib.util.find_spec("quantus") is not None:
            return True

        configured_path = self._env("QUANTUS_PATH")
        return bool(configured_path and Path(configured_path).exists())

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run explanation-quality evaluation wrapper with fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of explanation metric options.")

        action = str(request_params.get("action", "evaluate_explanations")).strip().lower()
        if not action:
            raise ValueError("action cannot be empty.")

        if self.is_airgapped:
            # Tactical requirement: deterministic confidence rehearsal in airgapped theaters.
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
                "error": "quantus package is not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
                "requested_action": action,
            }

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": action,
            "metric_family": str(request_params.get("metric_family", "robustness")),
            "detail": "Quantus wrapper ready for local explanation-quality benchmarking.",
        }
