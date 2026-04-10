"""Adapter for ODIN command-and-control information workflows.

Military/tactical context:
This wrapper supports deterministic checks for C2 data-management readiness so
mission staff can maintain command intent and force-state visibility offline.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Odinc2isAdapter(IntegrationAdapter):
    """S3M wrapper for ODIN C2IS integration workflows."""

    integration_id = "odin-c2is"
    domain = "swarm"
    _DEFAULT_OPERATION = "synchronize_c2_tracks"
    _COMMAND_CANDIDATES = ("java", "mvn", "docker")
    _MODULE_CANDIDATES = ("requests",)
    _ENV_PATH_KEYS = ("ODIN_C2IS_PATH", "ODIN_C2IS_ROOT")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.odin-c2is")

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
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate C2 synchronization requests before wrapper execution."""
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
        if len(json.dumps(normalized)) > 25000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata used by sovereign C2 integration orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "ODIN (C2IS)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/syncpoint/ODIN"),
            license=str(raw.get("license") or "(Archived)"),
            description=str(
                raw.get("description")
                or "Open-source Command and Control Information System alternative."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["c2_track_management", "order_synchronization", "operational_picture_support"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local ODIN runtime prerequisites without remote dependencies."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if any(importlib.util.find_spec(module) for module in self._MODULE_CANDIDATES):
            return True

        for env_key in self._ENV_PATH_KEYS:
            configured = self._env(env_key)
            if configured and Path(configured).expanduser().exists():
                return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute ODIN wrapper behavior with deterministic fixture fallback."""
        try:
            safe_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning odin-c2is fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
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
                "operation": operation,
                "request": safe_params,
                "message": "odin-c2is runtime is not installed or configured locally.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "odin-c2is dependencies validated for local command-and-control workflows.",
        }
