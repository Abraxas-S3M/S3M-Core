"""Adapter for PrimAITE.

Military/tactical context:
This wrapper connects S3M workflows to cyber-defense AI training environments
so operators can evaluate autonomous defensive behaviors against hostile network
conditions while remaining fully sovereign and offline-capable.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PrimaiteAdapter(IntegrationAdapter):
    """S3M integration adapter for PrimAITE."""

    integration_id = "primaite"
    domain = "military"
    _COMMAND_CANDIDATES = ("primaite", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.primaite")

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
        """Return PrimAITE metadata for cyber-defense training orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "PrimAITE"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE"
            ),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Primary AI Training Environment for military-oriented cyber-defense training and evaluation."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["cyber_training_episode", "defender_policy_eval", "resilience_scenario_replay"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local tool availability for sovereign cyber training."""
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
        """Wrap cyber-defense training operations with deterministic fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = str(request.get("operation", "cyber_training_episode")).strip().lower()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")
        if any(char in operation for char in (";", "|", "&", "`", "$", "\n", "\r")):
            raise ValueError("operation contains unsafe characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic cyber range rehearsals in denied-connectivity enclaves.
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
                "error": "primaite is not installed or configured",
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
            "note": "Local PrimAITE tooling detected for sovereign cyber-defense training workflows.",
        }
