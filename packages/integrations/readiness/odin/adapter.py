"""Adapter for ODIN command-and-control readiness views.

Military/tactical context:
This wrapper captures personnel and situational-awareness summaries for command
posts so readiness decisions can be rehearsed with deterministic outputs under
airgapped, contested operating conditions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OdinAdapter(IntegrationAdapter):
    """S3M integration adapter for ODIN personnel and SA readiness workflows."""

    integration_id = "odin"
    domain = "readiness"
    _COMMAND_CANDIDATES = ("odin", "docker", "docker-compose")
    _SUPPORTED_OPERATIONS = {"c2_personnel_overview", "situational_awareness_roster", "readiness_snapshot"}

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical auditability: keep a stable logger namespace across deployments.
        self.logger = logging.getLogger("s3m.integrations.readiness.odin")

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
        """Validate operator requests before command-readiness orchestration."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise TypeError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("all params keys must be strings")

        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload exceeds maximum size")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for command-readiness orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "ODIN"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/syncpoint/ODIN"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Open-source Command & Control system with personnel/SA views"
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["command_post_roster_visibility", "situational_awareness_panels", "personnel_readiness_briefing"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime availability without external API calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace("+", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute command-readiness workflow with deterministic offline fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "readiness_snapshot").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning fixture for operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
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
                "message": "ODIN tooling is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "runtime",
            "operation": operation,
            "request": request,
            "message": "Local ODIN runtime detected; command-readiness processing remains offline.",
        }
