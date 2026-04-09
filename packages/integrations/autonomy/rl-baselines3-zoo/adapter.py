"""rl-baselines3-zoo integration adapter for S3M autonomy training pipelines.

Military/tactical context:
This wrapper helps mission engineers package repeatable RL training plans for
edge-deployable policies used in autonomous platform maneuver and coordination.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RlBaselines3ZooAdapter(IntegrationAdapter):
    """Adapter for rl-baselines3-zoo training orchestration."""

    integration_id = "rl-baselines3-zoo"
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
            name=str(raw.get("name") or "rl-baselines3-zoo"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "unknown"),
            description=str(
                raw.get("description")
                or "SB3 training and tuning wrapper for tactical autonomy policy optimization."
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
        return importlib.util.find_spec("rl_zoo3") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary of tactical training options.")

        action = str(params.get("action", "build_training_plan")).strip().lower()
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

        if action == "build_training_plan":
            env_id = str(params.get("env_id", "CartPole-v1")).strip()
            algo = str(params.get("algo", "ppo")).strip().lower()
            total_steps = int(params.get("total_steps", 500_000))
            if total_steps <= 0:
                raise ValueError("total_steps must be positive.")
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "status": "planned",
                "plan": {
                    "algo": algo,
                    "env_id": env_id,
                    "total_steps": total_steps,
                    "command": f"python train.py --algo {algo} --env {env_id} -n {total_steps}",
                },
            }
        if action == "describe":
            return {
                "integration_id": self.integration_id,
                "mode": self.mode,
                "status": "ok",
                "detail": "rl-baselines3-zoo wrapper ready for local hyperparameter sweep planning.",
            }
        raise ValueError(f"Unsupported action: {action}")
