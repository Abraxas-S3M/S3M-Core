"""Adapter for dis-tutorial.

Military/tactical context:
This wrapper provides deterministic access to DIS doctrine and implementation
guidance so simulation officers can rehearse IEEE-1278 data-link procedures
inside sovereign, airgapped mission-planning enclaves.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class DisTutorialAdapter(IntegrationAdapter):
    """S3M integration adapter for dis-tutorial tactical reference workflows."""

    integration_id = "dis-tutorial"
    domain = "interop"
    _COMMAND_CANDIDATES = ("dis-tutorial", "mkdocs", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: fixed logger namespace supports after-action audit correlation.
        self.logger = logging.getLogger("s3m.integrations.interop.dis-tutorial")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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

    def get_manifest(self) -> IntegrationManifest:
        """Load interoperability metadata used by command-post simulation orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "dis-tutorial"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/open-dis/dis-tutorial"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Comprehensive handbook and tutorial for DIS concepts, implementation, and best practices."
            ),
            integration_type=str(raw.get("integration_type") or "reference"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["dis-doctrine-reference", "pdu-field-guidance", "training-scenario-brief-support"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local DIS tutorial toolchain or fixture readiness in sovereign mode."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(cmd) for cmd in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Serve DIS tutorial lookup workflow with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", "status")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning DIS tutorial rehearsal fixture.")
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
                "error": "dis-tutorial tooling is not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "DIS tutorial assets are available for mission-simulation briefing support.",
        }
