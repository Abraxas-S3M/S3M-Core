"""Adapter for C2SIMArtifacts.

Military/tactical context:
This wrapper supports sovereign handling of C2SIM schemas and reference artifacts
so coalition command-post exercises can validate message conformance in
airgapped and contested environments.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class C2simartifactsAdapter(IntegrationAdapter):
    """S3M integration adapter for C2SIMArtifacts interoperability workflows."""

    integration_id = "c2simartifacts"
    domain = "interop"
    _COMMAND_CANDIDATES = ("c2simartifacts", "xmllint", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: fixed logger namespace preserves chain-of-custody traces.
        self.logger = logging.getLogger("s3m.integrations.interop.c2simartifacts")

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
        """Load C2SIM manifest metadata for command-and-control interoperability services."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "C2SIMArtifacts"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/OpenC2SIM/C2SIMArtifacts"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Artifacts, schemas, and reference implementations for C2SIM standard."
            ),
            integration_type=str(raw.get("integration_type") or "reference"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["c2sim-schema-validation", "reference-artifact-indexing", "message-conformance-checking"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local C2SIM schema toolchain availability or fixture readiness."""
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
        """Execute C2SIM artifact wrapper flow with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", "status")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning C2SIMArtifacts fixture output.")
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
                "error": "c2simartifacts tooling is not installed or configured",
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
            "note": "Local C2SIM artifact resources are ready for sovereign conformance workflows.",
        }
