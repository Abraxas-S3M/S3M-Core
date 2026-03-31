"""Policy persistence for tactical autonomy reinforcement learning models.

Policies are stored locally to support fully air-gapped deployments where
models must be retained and audited on platform.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import pickle
import shutil
from typing import Any, Dict, List, Optional, Tuple


class PolicyRegistry:
    """Store and retrieve trained policy artifacts with metadata sidecars."""

    def __init__(self, policies_dir: str = "models/policies/") -> None:
        self.policies_dir = policies_dir
        os.makedirs(self.policies_dir, exist_ok=True)

    def _policy_dir(self, name: str) -> str:
        return os.path.join(self.policies_dir, name)

    def _metadata_path(self, name: str) -> str:
        return os.path.join(self._policy_dir(name), "metadata.json")

    def _policy_path(self, name: str) -> str:
        return os.path.join(self._policy_dir(name), "policy.pkl")

    def save_policy(self, name: str, policy_object: Any, metadata: Dict[str, Any]) -> None:
        """Persist policy and metadata for tactical replay and reuse."""
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        directory = self._policy_dir(name)
        os.makedirs(directory, exist_ok=True)
        policy_path = self._policy_path(name)
        metadata_path = self._metadata_path(name)

        with open(policy_path, "wb") as policy_file:
            pickle.dump(policy_object, policy_file)

        enriched_metadata = {
            "name": name,
            "timestamp": metadata.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "training_env": metadata.get("training_env", "unknown"),
            "reward_config": metadata.get("reward_config", {}),
            "steps_trained": int(metadata.get("steps_trained", 0)),
            "performance_metrics": metadata.get("performance_metrics", {}),
            "backend": metadata.get("backend", "builtin"),
            "algorithm": metadata.get("algorithm", "unknown"),
        }
        with open(metadata_path, "w", encoding="utf-8") as metadata_file:
            json.dump(enriched_metadata, metadata_file, indent=2)

    def load_policy(self, name: str) -> Tuple[Any, Dict[str, Any]]:
        """Load policy object and metadata; raise clear errors when unavailable."""
        policy_path = self._policy_path(name)
        metadata_path = self._metadata_path(name)
        if not os.path.exists(policy_path) or not os.path.exists(metadata_path):
            raise FileNotFoundError(f"policy not found: {name}")
        try:
            with open(policy_path, "rb") as policy_file:
                policy_object = pickle.load(policy_file)
            with open(metadata_path, "r", encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
            return policy_object, metadata
        except (pickle.PickleError, json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"corrupt policy artifacts for: {name}") from exc

    def list_policies(self) -> List[Dict[str, Any]]:
        """List policy metadata for command authority selection decisions."""
        policies: List[Dict[str, Any]] = []
        try:
            names = sorted(os.listdir(self.policies_dir))
        except FileNotFoundError:
            return policies

        for name in names:
            metadata_path = self._metadata_path(name)
            if not os.path.exists(metadata_path):
                continue
            try:
                with open(metadata_path, "r", encoding="utf-8") as metadata_file:
                    metadata = json.load(metadata_file)
                policies.append(metadata)
            except (json.JSONDecodeError, OSError):
                # Corrupted metadata is skipped so the registry remains usable.
                continue
        return policies

    def delete_policy(self, name: str) -> None:
        """Remove policy artifacts from local storage."""
        shutil.rmtree(self._policy_dir(name), ignore_errors=True)

    def get_best_policy(self, env_name: str) -> Optional[str]:
        """Return highest-performing policy name for the specified environment."""
        candidates = [p for p in self.list_policies() if p.get("training_env") == env_name]
        if not candidates:
            return None

        def score(metadata: Dict[str, Any]) -> float:
            metrics = metadata.get("performance_metrics", {})
            mean_reward = metrics.get("mean_reward", metrics.get("reward", 0.0))
            try:
                return float(mean_reward)
            except (TypeError, ValueError):
                return 0.0

        best = max(candidates, key=score)
        return str(best.get("name"))
