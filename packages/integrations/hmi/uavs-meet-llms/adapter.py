"""UAVs_Meet_LLMs integration adapter for S3M HMI operations.

Military/tactical context:
This wrapper supports explainable vision-language UAV mission support so
operators can review low-altitude autonomy outputs during disconnected maneuvers.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class UavsMeetLlmsAdapter(IntegrationAdapter):
    """Adapter for UAV and LLM cooperative mission workflows."""

    integration_id = "uavs-meet-llms"
    domain = "hmi"
    _OPTIONAL_MODULES = ("uavs_meet_llms", "uavs_llm")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.hmi.uavs-meet-llms")
        self._root = Path(__file__).resolve().parent

    def _manifest_path(self) -> Path:
        return self._root / "manifest.yaml"

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
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("manifest.yaml must contain a YAML mapping.")
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load wrapper metadata for orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "UAVs_Meet_LLMs"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Vision-language UAV teaming for low-altitude agentic mobility support."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["mission_planning", "vision_language_reasoning", "uav_tasking"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate offline-safe availability of the local integration runtime."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("UAVS_MEET_LLMS_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        manifest_vendor_path = self.get_manifest().vendor_path
        if manifest_vendor_path and Path(manifest_vendor_path).exists():
            return True

        return any(importlib.util.find_spec(module_name) for module_name in self._OPTIONAL_MODULES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run mission-support wrapper flow with deterministic fixture fallback."""
        request_params = params or {}
        if not isinstance(request_params, dict):
            raise ValueError("params must be a dictionary of UAV mission options.")

        action = str(request_params.get("action", "plan_sortie")).strip().lower()
        if not action:
            raise ValueError("action cannot be empty.")

        if self.is_airgapped:
            # Tactical requirement: return deterministic rehearsal data in denied networks.
            fixture_payload = self._read_fixture("sample_response.json")
            payload = dict(fixture_payload) if isinstance(fixture_payload, dict) else {"result": fixture_payload}
            payload.update(
                {
                    "integration_id": self.integration_id,
                    "domain": self.domain,
                    "mode": "airgapped",
                    "source": "fixture",
                    "requested_action": action,
                }
            )
            payload.setdefault("status", "ok")
            return payload

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "error": "UAVs_Meet_LLMs runtime not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
                "requested_action": action,
            }

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": action,
            "mission_profile": str(request_params.get("mission_profile", "urban_recon")),
            "detail": "Wrapper is ready for local UAV-LLM mission assistance pipelines.",
        }
