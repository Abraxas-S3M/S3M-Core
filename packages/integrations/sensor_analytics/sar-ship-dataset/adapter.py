"""Adapter for SAR-Ship-Dataset curation and dataset readiness workflows.

Military/tactical context:
This wrapper supports dataset governance for maritime models, ensuring command
teams can audit label coverage before theater-specific retraining.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SarShipDatasetAdapter(IntegrationAdapter):
    """S3M adapter for SAR-Ship-Dataset metadata and sample access."""

    integration_id = "sar-ship-dataset"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ("python3", "tar", "unzip")
    _DEFAULT_OPERATION = "query_dataset_statistics"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_analytics.sar-ship-dataset")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}

        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}

        if not isinstance(raw, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise TypeError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            return json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for SAR training dataset orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "SAR-Ship-Dataset"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/CAESAR-Radi/SAR-Ship-Dataset"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "39,729 labeled SAR ship chips from Gaofen-3 and Sentinel-1 for maritime model training."
            ),
            integration_type=str(raw.get("integration_type") or "dataset"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["dataset_metadata_query", "label_distribution_audit", "chip_inventory_summary"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local dataset/runtime availability without external network access."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run dataset metadata queries with deterministic fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical requirement: reproducible dataset stats support model accreditation boards.
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "source": "runtime",
                "operation": operation,
                "request": request,
                "message": "SAR-Ship-Dataset is not installed or configured in local storage.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "accepted",
            "source": "runtime",
            "operation": operation,
            "request": request,
            "message": "Local SAR dataset readiness checks passed; retrieval execution remains orchestrator-governed.",
        }
