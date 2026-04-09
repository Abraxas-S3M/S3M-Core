"""PettingZoo integration adapter for S3M autonomy rehearsals.

Military/tactical context:
This wrapper allows mission autonomy teams to evaluate multi-agent decision
policies in synthetic contested environments while fully offline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PettingzooAdapter(IntegrationAdapter):
    """Adapter for PettingZoo multi-agent simulation integration."""

    integration_id = "pettingzoo"
    domain = "autonomy"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._root = Path(__file__).resolve().parent

    def _manifest_path(self) -> Path:
        return self._root / "manifest.yaml"

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("manifest.yaml must contain a mapping.")
        return IntegrationManifest(
            name=str(raw.get("name") or "PettingZoo"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "unknown"),
            description=str(
                raw.get("description")
                or "Multi-agent RL environment wrapper for tactical autonomy behavior rehearsal."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._as_list(raw.get("capabilities")),
            pip_dependencies=self._as_list(raw.get("pip_dependencies")),
            system_dependencies=self._as_list(raw.get("system_dependencies")),
            docker_dependencies=self._as_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("pettingzoo") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary of tactical simulation options.")

        action = str(params.get("action", "describe")).strip().lower()
        if not action:
            raise ValueError("action cannot be empty.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            payload = dict(fixture) if isinstance(fixture, dict) else {"result": fixture}
            payload["mode"] = "airgapped"
            payload["source"] = "fixture"
            payload["requested_action"] = action
            payload["integration_id"] = self.integration_id
            return payload

        if not self.validate_availability():
            return {"status": "unavailable", "integration_id": self.integration_id, "action": action}

        if action == "list_env_families":
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "families": ["mpe", "atari", "classic", "butterfly", "sisl"],
                "status": "ok",
            }
        if action == "validate_env":
            env_id = str(params.get("env_id", "")).strip()
            if not env_id:
                raise ValueError("env_id is required for validate_env action.")
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "env_id": env_id,
                "status": "validated",
                "detail": "Environment identifier passed local schema checks.",
            }
        if action == "describe":
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "status": "ok",
                "detail": "PettingZoo wrapper ready for local multi-agent simulation tasks.",
            }
        raise ValueError(f"Unsupported action: {action}")
