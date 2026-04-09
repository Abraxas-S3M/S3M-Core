"""news-briefing-generator adapter for S3M intelligence brief workflows.

Military/tactical context:
This wrapper supports local-LMM briefing synthesis from curated feed ingestion,
allowing analysts to produce updates in disconnected command environments.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class NewsBriefingGeneratorAdapter(IntegrationAdapter):
    """Wrap local RSS-to-brief flows with deterministic offline support."""

    integration_id = "news-briefing-generator"
    domain = "intel"
    _SUPPORTED_OPERATIONS = {"generate_brief", "cluster_topics", "summarize_feeds"}

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.intel.news-briefing-generator")

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
        """Validate untrusted payloads before tactical processing."""
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
            name=str(raw.get("name") or "news-briefing-generator"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/grbtm/news-briefing-generator"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Local LLM-powered news briefing from RSS feeds with clustering and summarization."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["rss_ingestion", "topic_clustering", "brief_summarization"]
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
        return any(shutil.which(command) for command in ("news-briefing-generator", "python3"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run local briefing pipeline wrapper with secure fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "generate_brief").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture-backed local briefing output for mission rehearsal.")
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
            # External calls are blocked for sovereign intelligence posture.
            "message": "Runtime dependency check complete; external invocation is disabled by policy.",
            "request": safe_params,
        }
