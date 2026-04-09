"""briefing-agent integration adapter for S3M intelligence operations.

Military/tactical context:
This wrapper stages multi-agent briefing outputs for command decision support,
allowing mission analysts to rehearse production pipelines in airgapped nodes.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class BriefingAgentAdapter(IntegrationAdapter):
    """Wrap multi-agent briefing workflows with sovereign-safe controls."""

    integration_id = "briefing-agent"
    domain = "intel"
    _SUPPORTED_OPERATIONS = {"produce_brief", "agent_consensus", "threat_digest"}

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.intel.briefing-agent")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted payloads before tactical workflow handling."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        safe_payload = json.loads(json.dumps(params))
        if len(json.dumps(safe_payload)) > 20000:
            raise ValueError("params payload is too large")
        return safe_payload

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "briefing-agent"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/alexnix300/briefing-agent"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Multi-agent system for enhanced production briefings using LLMs."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["multi_agent_reasoning", "brief_generation", "source_prioritization"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies") or ["python3"]),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return any(shutil.which(command) for command in ("briefing-agent", "python3"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute multi-agent briefing wrapper with fixture-safe fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "produce_brief").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture-backed multi-agent brief for offline operations center use.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "available": True,
                "status": "ok",
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        availability = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "source": "runtime",
            "available": availability,
            "status": "ready" if availability else "unavailable",
            # Sovereign policy: wrapper does not invoke remote LLM providers.
            "message": "Runtime dependency check complete; external invocation is disabled by policy.",
            "request": safe_params,
        }
