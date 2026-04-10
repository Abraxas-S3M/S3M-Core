"""Adapter for ArcticShadowTracker dark-vessel analytics workflows.

Military/tactical context:
This wrapper supports maritime interdiction operations by correlating AIS and
satellite evidence to flag vessels attempting to evade cooperative tracking.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ArcticshadowtrackerAdapter(IntegrationAdapter):
    """S3M adapter for dark-vessel detection in high-latitude waters."""

    integration_id = "arcticshadowtracker"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ("python3", "sqlite3")
    _DEFAULT_OPERATION = "detect_dark_vessel_activity"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Fixed logger namespace is required for tactical incident traceability.
        self.logger = logging.getLogger("s3m.integrations.sensor_analytics.arcticshadowtracker")

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
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return loaded

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            return json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for dark-vessel intelligence workflows."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "ArcticShadowTracker"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/henrfo/ArcticShadowTracker"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "AIS and satellite fusion pipeline for dark-vessel detection."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get("capabilities")
                or ["ais_satellite_correlation", "dark_vessel_flagging", "maritime_threat_scoring"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local analytics runtime readiness without external connectivity."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute dark-vessel wrapper with deterministic airgapped fixture output."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string up to 64 characters")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
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
                "request": safe_params,
                "message": "ArcticShadowTracker dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "runtime",
            "operation": operation,
            "request": safe_params,
            "message": "Local dark-vessel analytics runtime detected; sovereign execution can proceed.",
        }
