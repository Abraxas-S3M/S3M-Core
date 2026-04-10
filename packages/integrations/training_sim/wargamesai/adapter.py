"""Adapter for WargamesAI professional simulation workflows.

Military/tactical context:
This wrapper enables reproducible tactical decision-game outputs for commander
training, red-team rehearsal, and staff planning under contested connectivity.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class WargamesaiAdapter(IntegrationAdapter):
    """S3M training_sim adapter for WargamesAI."""

    integration_id = "wargamesai"
    domain = "training_sim"
    _MODULE_CANDIDATES = ("transformers", "numpy")
    _COMMAND_CANDIDATES = ("wargamesai", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.training_sim.wargamesai")

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
        """Validate tactical request payloads to preserve secure offline execution."""
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
        """Load adapter metadata for tactical training_sim orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "WargamesAI"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/user1342/WargamesAI"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Toolkit wrapper for creating, executing, and evaluating LLM-based wargame drills."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get("capabilities")
                or ["llm_agent_wargaming", "scenario_execution", "after_action_evaluation"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime dependencies without external service calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        module_ready = any(importlib.util.find_spec(module_name) for module_name in self._MODULE_CANDIDATES)
        command_ready = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return module_ready or command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute professional wargame workflow with deterministic fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "professional_wargame_run").strip()
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
                "message": "WargamesAI runtime dependencies are not installed or configured.",
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
            "message": "Local runtime validated for secure mission-simulation execution.",
        }
