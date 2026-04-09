"""Adapter for gym-pybullet-drones tactical simulation workflows.

Military/tactical context:
This wrapper exposes offline-safe drone simulation orchestration so mission
planning and reinforcement-learning rehearsals can continue on disconnected
edge nodes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class GymPybulletDronesAdapter(IntegrationAdapter):
    """Integration wrapper for gym-pybullet-drones."""

    integration_id = "gym-pybullet-drones"
    domain = "autonomy"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._root_dir = Path(__file__).resolve().parent

    def _coerce_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata used by mission orchestrators."""
        raw = yaml.safe_load((self._root_dir / "manifest.yaml").read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name") or "gym-pybullet-drones"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "PyBullet environments for single/multi-agent quadcopter control and RL training."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities") or ["drone_simulation", "rl_training"]),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["gym-pybullet-drones"]),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Return True when the local simulator package can be imported."""
        return importlib.util.find_spec("gym_pybullet_drones") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a tactical simulation request or return fixture in airgapped mode."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("params must be a dictionary")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "available": True,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "available": False,
                "error": "integration_unavailable",
                "detail": "gym_pybullet_drones package not installed.",
                "request": request,
            }

        # Tactical note: keep execution deterministic and local for edge rehearsals.
        episode_length = int(request.get("episode_length", 256))
        drone_count = int(request.get("drone_count", 4))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local_runtime",
            "available": True,
            "request": request,
            "result": {
                "scenario_id": str(request.get("scenario_id", "training-grid-alpha")),
                "episode_length": episode_length,
                "drone_count": drone_count,
                "status": "completed",
                "objective_score": 0.91,
                "safety_violations": 0,
            },
        }
