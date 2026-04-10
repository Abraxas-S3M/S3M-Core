"""Adapter for warshard modern wargame simulation workflows.

Military/tactical context:
This wrapper provides deterministic battle-simulation payloads so mission teams
can rehearse tactical engagements while disconnected from external networks.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WarshardAdapter(IntegrationAdapter):
    """S3M training_sim adapter for warshard."""

    integration_id = "warshard"
    domain = "training_sim"
    _COMMAND_CANDIDATES = ("warshard", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.training_sim.warshard")

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
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate scenario input payload to protect tactical simulators."""
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
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata from local manifest for orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "warshard"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/qferre/warshard"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Simplified modern wargame adapter for tactical modeling and scenario rehearsal."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get("capabilities")
                or ["scenario_modeling", "tactical_simulation", "custom_api_handoff"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local warshard runtime availability for sovereign operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute modern-wargame wrapper with deterministic fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "combined_arms_engagement").strip()
        if not operation or len(operation) > 80:
            raise ValueError("operation must be a non-empty string with at most 80 characters")

        if self.is_airgapped:
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
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "warshard runtime dependencies are not installed or configured.",
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local runtime validated; tactical simulation can be orchestrated securely.",
        }
