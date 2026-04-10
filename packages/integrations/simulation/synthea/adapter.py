"""Adapter for Synthea synthetic medical simulation workflows.

Military/tactical context:
This wrapper supports logistics and casualty modeling rehearsals by exposing
a deterministic, airgapped-safe interface to synthetic patient generation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SyntheaAdapter(IntegrationAdapter):
    """S3M simulation adapter for Synthea scenario generation."""

    integration_id = "synthea"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("synthea", "java")
    _DEFAULT_OPERATION = "generate_casualty_cohort"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.synthea")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        path = self._manifest_path()
        if not path.exists():
            self.logger.warning("Manifest file missing: %s", path)
            return {}

        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", path)
            return {}

        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate tactical simulation requests before execution."""
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

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load simulation metadata used by mission orchestration."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "Synthea"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/synthetichealth/synthea"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Synthetic patient generator adapted for casualty and medical logistics simulation."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["casualty_generation", "medical_logistics_forecast", "scenario_population_modeling"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["java"]),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether the local Synthea runtime is available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        synthea_path = self._env("SYNTHEA_PATH").strip()
        if synthea_path:
            return Path(synthea_path).expanduser().exists()

        synthea_jar = self._env("SYNTHEA_JAR").strip()
        if synthea_jar:
            return Path(synthea_jar).expanduser().is_file()

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute synthetic population generation with offline-safe behavior."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION).strip().lower()

        if self.is_airgapped:
            self.logger.info("Returning fixture data for operation=%s", operation)
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
                "message": "Synthea runtime is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": request,
            "message": "Synthea adapter is available for local casualty/logistics simulation workflows.",
        }
