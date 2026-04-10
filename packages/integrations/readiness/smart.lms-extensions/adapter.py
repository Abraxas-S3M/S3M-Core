"""Adapter for Smart.LMS extensions readiness workflows.

Military/tactical context:
This wrapper exposes training and certification readiness snapshots so command
staff can verify personnel qualification posture in disconnected operations.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import re
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SmartlmsExtensionsAdapter(IntegrationAdapter):
    """S3M integration wrapper for Smart.LMS extension capabilities."""

    integration_id = "smart.lms-extensions"
    domain = "readiness"
    _COMMAND_CANDIDATES = ("learnhouse", "smart-lms", "smartlms", "lms")
    _MODULE_CANDIDATES = ("learnhouse", "smart_lms", "smartlms")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: keep logger namespace stable for mission audit trails.
        self.logger = logging.getLogger("s3m.integrations.readiness.smart.lms-extensions")

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

    def get_manifest(self) -> IntegrationManifest:
        """Load wrapper metadata used by readiness orchestration pipelines."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Smart.LMS extensions"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Related forks of Smart.LMS / learnhouse"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Learning management extensions for certification and training readiness tracking."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["certification_tracking", "training_progress", "qualification_readiness"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local Smart.LMS tooling presence without external calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        if any(importlib.util.find_spec(module_name) for module_name in self._MODULE_CANDIDATES):
            return True
        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute readiness query or return deterministic airgapped fixture payload."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = str(request.get("operation", "readiness_summary")).strip().lower()
        if not operation or len(operation) > 64 or re.fullmatch(r"[a-z0-9_-]+", operation) is None:
            raise ValueError("operation must match ^[a-z0-9_-]{1,64}$")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning Smart.LMS fixture payload.")
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
                "error": "Smart.LMS extensions runtime is not installed or configured",
                "request": request,
            }

        # Tactical note: online mode still returns local status only to keep sovereign execution offline-safe.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-runtime",
            "status": "ready",
            "operation": operation,
            "request": request,
            "result": {
                "status": "ready",
                "readiness_signal": "training_pipeline_accessible",
            },
        }
