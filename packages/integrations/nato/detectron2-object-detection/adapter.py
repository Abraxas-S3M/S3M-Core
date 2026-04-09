"""Adapter for Detectron2 object-detection workflows.

Military/tactical context:
This wrapper provides deterministic battlefield object-detection rehearsal for
ISR pipelines in sovereign deployments where network egress is disallowed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Detectron2objectDetectionAdapter(IntegrationAdapter):
    """S3M integration adapter for Detectron2 mission-vision operations."""

    integration_id = "detectron2-object-detection"
    domain = "nato"
    _SUPPORTED_OPERATIONS = {"object_detection", "model_validation", "batch_inference"}
    _MODULE_CANDIDATES = ("detectron2",)

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}

        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}

        if not isinstance(loaded, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return loaded

    def get_manifest(self) -> IntegrationManifest:
        """Return adapter metadata for ISR and target-detection orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Detectron2 (object detection)")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Apache-2.0")),
            description=(
                "Object-detection wrapper for NATO-aligned visual ISR workloads, "
                "replication studies, and deterministic airgapped analysis drills."
            ),
            integration_type="adapter",
            capabilities=["object-detection", "vision-model-validation", "batch-inference"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Validate local Detectron2 runtime availability for tactical vision tasks."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        return any(importlib.util.find_spec(module_name) is not None for module_name in self._MODULE_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute detection wrapper flow with deterministic offline fallback."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "object_detection")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning Detectron2 fixture for ISR rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": request,
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
                "request": request,
                "message": "Detectron2 runtime is not installed on this host.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": request,
            "message": "Detectron2 runtime checks passed; live execution remains orchestrator-controlled.",
        }
