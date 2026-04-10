"""Adapter for WarAgent conflict simulation workflows.

Military/tactical context:
This wrapper provides offline-safe orchestration hooks for LLM-based
strategic conflict rehearsal in campaign planning and red-team analysis.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WaragentAdapter(IntegrationAdapter):
    """S3M simulation adapter for WarAgent campaign simulation."""

    integration_id = "waragent"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("waragent",)
    _DEFAULT_OPERATION = "simulate_conflict_turns"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.waragent")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        path = self._manifest_path()
        if not path.exists():
            self.logger.warning("Manifest file missing: %s", path)
            return {}

        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", path)
            return {}

        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate conflict-simulation requests before processing."""
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

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter metadata for strategic simulation planning."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "WarAgent"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/agiresearch/WarAgent"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "LLM-based multi-agent simulation of world wars and international conflicts."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["multi_agent_wargaming", "campaign_turn_simulation", "strategic_outcome_projection"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["python3"]),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether local WarAgent runtime artifacts are available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        waragent_path = self._env("WARAGENT_PATH").strip()
        if waragent_path:
            return Path(waragent_path).expanduser().exists()

        waragent_entry = self._env("WARAGENT_ENTRYPOINT").strip()
        if waragent_entry:
            return Path(waragent_entry).expanduser().is_file()

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute conflict simulation with deterministic airgapped fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION).strip().lower()

        if self.is_airgapped:
            self.logger.info("Returning fixture data for operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": request,
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
                "request": request,
                "message": "WarAgent runtime is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": request,
            "message": "WarAgent adapter is available for local strategic conflict simulation.",
        }
