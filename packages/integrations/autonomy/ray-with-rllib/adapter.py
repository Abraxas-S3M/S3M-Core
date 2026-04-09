"""Ray RLlib integration wrapper for distributed tactical policy training."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RaywithRllibAdapter(IntegrationAdapter):
    """Coordinate Ray RLlib workflows for contested swarm-training simulations."""

    integration_id = "ray-with-rllib"
    domain = "autonomy"
    _required_modules = ("ray", "ray.rllib")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.autonomy.ray-with-rllib")
        self._manifest_cache: IntegrationManifest | None = None

    @property
    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load wrapper metadata used by mission orchestration registries."""
        if self._manifest_cache is not None:
            return self._manifest_cache

        raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        self._manifest_cache = IntegrationManifest(
            name=str(raw.get("name") or "ray (with RLlib)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/ray-project/ray"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Scalable RL orchestration for resilient multi-agent tactical training."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities", ["distributed_training", "multi_agent_rl"])],
            pip_dependencies=[str(item) for item in raw.get("pip_dependencies", ["ray[rllib]"])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )
        return self._manifest_cache

    def _module_available(self, module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, AttributeError, ValueError):
            return False

    def validate_availability(self) -> bool:
        """Verify local runtime support before tactical autonomy tasks execute."""
        if self.is_airgapped:
            return (self._fixture_dir / "sample_response.json").exists()
        return all(self._module_available(module_name) for module_name in self._required_modules)

    def _sanitize_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for safe tactical execution.")

        sanitized: dict[str, Any] = {}
        for key, value in params.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            elif isinstance(value, list):
                sanitized[key] = [item for item in value if isinstance(item, (str, int, float, bool))]
        return sanitized

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run or emulate distributed RL tasks for mission rehearsal pipelines."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "train_swarm_policy")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
                "available": self.validate_availability(),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "detail": "Ray RLlib is not installed on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "detail": "Ray RLlib runtime detected for distributed autonomy workloads.",
            "parameters": safe_params,
        }
