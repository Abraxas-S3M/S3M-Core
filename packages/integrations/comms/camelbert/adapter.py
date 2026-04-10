"""Adapter for CAMeLBERT Arabic NLP communication analysis.

Military/tactical context:
This wrapper supports secure communications intelligence by extracting Arabic
message intent and tactical category signals for command prioritization.
"""

from __future__ import annotations

import json
import logging
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class CamelbertAdapter(IntegrationAdapter):
    """S3M comms adapter for CAMeLBERT Arabic NLP tasks."""

    integration_id = "camelbert"
    domain = "comms"
    _DEFAULT_OPERATION = "classify_signal_intent"
    _REQUIRED_MODULES = ("transformers", "torch")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.comms.camelbert")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate Arabic communication payload parameters before processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized, ensure_ascii=True)) > 25000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return CAMeLBERT metadata for comms integration discovery."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "CAMeLBERT"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/CAMeL-Lab/CAMeLBERT"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Arabic pre-trained model collection for classification and summarization tasks."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["arabic_intent_classification", "topic_detection", "offline_fixture_replay"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies") or ["transformers", "torch"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local NLP runtime dependencies without any external network usage."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("CAMELBERT_PATH").strip()
        if configured_path:
            return Path(configured_path).expanduser().exists()

        return all(find_spec(module_name) is not None for module_name in self._REQUIRED_MODULES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute CAMeLBERT wrapper with deterministic fixture replay offline."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip().lower()

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning CAMeLBERT fixture for operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "CAMeLBERT runtime dependencies are missing on this sovereign node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local prerequisites passed; model inference execution is orchestrator-managed.",
        }
