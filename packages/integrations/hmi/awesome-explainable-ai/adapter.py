"""HMI integration wrapper for awesome-explainable-ai.

Military/tactical context:
Commanders and human-machine teaming operators need transparent AI rationale
references before approving autonomous recommendations. This adapter provides a
standardized, airgapped-safe interface for retrieving explainable AI summaries
and frontier methods in denied communications environments.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeExplainableAiAdapter(IntegrationAdapter):
    """Adapter for mission-safe explainability knowledge retrieval."""

    integration_id = "awesome-explainable-ai"
    domain = "hmi"

    _repo_env_var = "AWESOME_EXPLAINABLE_AI_PATH"
    _fallback_binary = "git"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.hmi.awesome-explainable-ai")

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for tactical orchestration registries."""
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}

        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-explainable-ai"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/rushrukh/awesome-explainable-ai"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Summaries and frontier research on Explainable AI methods for operator-facing trust and audit workflows."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities")),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local availability without any external network dependency."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        local_repo_path = self._env(self._repo_env_var)
        if local_repo_path:
            return Path(local_repo_path).expanduser().exists()

        return shutil.which(self._fallback_binary) is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute explainability reference retrieval for tactical operators."""
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("execute params must be a mapping/dictionary")

        if self.is_airgapped:
            self.logger.info("Returning fixture response for airgapped explainability briefing.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": str(params.get("operation", "xai_frontier_brief")),
                "available": True,
                "data": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        local_repo_path = self._env(self._repo_env_var)
        focus_area = str(params.get("focus_area", "model_transparency"))

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "operation": str(params.get("operation", "xai_frontier_brief")),
            "available": available,
            "repository_path": local_repo_path,
            "focus_area": focus_area,
            "data": {
                "status": "available" if available else "unavailable",
                "note": (
                    "Set AWESOME_EXPLAINABLE_AI_PATH for pinned local content during "
                    "disconnected mission deployments."
                ),
            },
        }
