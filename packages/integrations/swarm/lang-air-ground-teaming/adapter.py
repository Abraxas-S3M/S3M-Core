"""Adapter for language-guided air-ground teaming mission workflows.

Military/tactical context:
This wrapper validates language-driven air and ground collaboration pipelines
that convert commander intent into coordinated actions in unknown terrain while
maintaining sovereign, fully offline execution controls.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class LangAirGroundTeamingAdapter(IntegrationAdapter):
    """S3M integration adapter for lang-air-ground-teaming."""

    integration_id = "lang-air-ground-teaming"
    domain = "swarm"
    _COMMAND_CANDIDATES = (
        "lang-air-ground-teaming",
        "air_ground_teaming",
        "mission_language_planner",
    )
    _MODULE_CANDIDATES = ("lang_air_ground_teaming",)
    _DEFAULT_OPERATION = "language_conditioned_team_plan"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(f"s3m.integrations.swarm.{self.integration_id}")

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
            self.logger.exception("Failed to parse manifest YAML: %s", manifest_path)
            return {}

        if not isinstance(raw, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate mission intent inputs before tactical planning execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure air-ground planning.")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings.")

        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable.") from exc

        if len(json.dumps(normalized)) > 50_000:
            raise ValueError("params payload is too large.")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return lang-air-ground-teaming metadata loaded from manifest.yaml."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "lang-air-ground-teaming")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(
                raw.get(
                    "source_url",
                    "https://github.com/KumarRobotics/lang-air-ground-teaming",
                )
            ),
            license=str(raw.get("license", "MIT")),
            description=str(
                raw.get("description")
                or "Air-ground collaboration for language-specified missions in unknown environments."
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get(
                    "capabilities",
                    [
                        "language_to_mission_translation",
                        "air_ground_task_allocation",
                        "unknown_environment_exploration",
                    ],
                )
            ),
            system_dependencies=self._coerce_list(
                raw.get("system_dependencies", ["python3", "ros2"])
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check whether local planning dependencies are available on this node."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH") or self._env(f"{env_prefix}_ROOT")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        if any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute language-guided teaming wrapper with deterministic fixture fallback."""
        try:
            safe_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(safe_params.get("operation", self._DEFAULT_OPERATION))
        if self.is_airgapped:
            # Mission rehearsal cells use fixture replay to emulate language-to-task planning.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "result": self._read_fixture("sample_response.json"),
                "request": safe_params,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "lang-air-ground-teaming runtime dependencies are not installed or configured on this node.",
                "request": safe_params,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": safe_params,
            "note": "lang-air-ground-teaming adapter is ready for language-specified air-ground mission planning.",
        }
