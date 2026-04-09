"""Adapter for GLAWS (SpearBot).

Military/tactical context:
This wrapper provides sovereign control-surface checks for ethics-research
autonomous weapons prototypes so red-team and legal-review cells can rehearse
policy constraints in isolated test enclaves.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class GlawsspearbotAdapter(IntegrationAdapter):
    """S3M integration adapter for GLAWS (SpearBot)."""

    integration_id = "glaws-spearbot"
    domain = "military"
    _COMMAND_CANDIDATES = ("spearbot", "glaws", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.glaws-spearbot")

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
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(payload, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata for ethics-focused military autonomy integration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "GLAWS (SpearBot)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/westpoint-robotics/GLAWS"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Ground Lethal Autonomous Weapons System prototype adapter for ethics research exercises."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["ethics_scenario_rehearsal", "control_loop_status", "policy_gate_validation"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local tooling availability without network interactions."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap ethics-research control checks with fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = str(request.get("operation", "ethics_scenario_rehearsal")).strip().lower()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")
        if any(char in operation for char in (";", "|", "&", "`", "$", "\n", "\r")):
            raise ValueError("operation contains unsafe characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic legal/ethical rehearsal in disconnected labs.
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "glaws-spearbot is not installed or configured",
                "operation": operation,
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "note": "Local GLAWS tooling detected for controlled ethics-research workflow orchestration.",
        }
