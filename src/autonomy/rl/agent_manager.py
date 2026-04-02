"""RL agent management with robust offline fallback for tactical autonomy.

This module abstracts multiple RL backends to ensure Layer 03 autonomy remains
operational in air-gapped deployments where optional training libraries may be
absent on forward-deployed compute nodes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Callable, Dict, List, Optional
import uuid

from .environments import MilitaryEnvironment
from .policy_registry import PolicyRegistry

try:  # Air-gap safe optional import.
    from src.autonomy.decision_engine import ProbabilisticDecisionEngine
except Exception:  # pragma: no cover - optional dependency path
    ProbabilisticDecisionEngine = None  # type: ignore[assignment]


@dataclass
class RewardConfig:
    """Weights used when composing tactical rewards during RL training."""

    mission_completion: float = 1.0
    threat_avoidance: float = 1.0
    efficiency: float = 0.5
    formation: float = 0.7
    roe_compliance: float = 1.2


@dataclass
class _ManagedAgent:
    """Internal record for active RL agents across backend implementations."""

    agent_id: str
    env: Any
    algorithm: str
    backend: str
    model: Any = None
    trained_steps: int = 0
    episodes: int = 0
    training_metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    loaded_policy_name: Optional[str] = None


class _BuiltinPolicy:
    """[BUILTIN] Rule-based fallback — install ray or stable-baselines3 for trained policies."""

    def __init__(self, env: Any, algorithm: str = "RULE_BASED") -> None:
        self.env = env
        self.algorithm = algorithm
        self.reward_baseline: List[float] = []

    def _distance_2d(self, a: List[float], b: List[float]) -> float:
        return math.dist((a[0], a[1]), (b[0], b[1]))

    def predict(self, observation: Dict[str, Any]) -> int:
        # Tactical rationale: survive first, then progress toward objective.
        waypoint = observation.get("mission_waypoint", [0.0, 0.0, 0.0])
        pos = observation.get("agent_position", [0.0, 0.0, 0.0])
        heading = float(observation.get("agent_heading", [0.0])[0]) % 360.0
        speed = float(observation.get("agent_speed", [0.0])[0])
        threat_positions = observation.get("threat_positions", [])
        roe = observation.get("rules_of_engagement", "weapons_hold")

        nearest_idx = None
        nearest_dist = float("inf")
        for idx, threat in enumerate(threat_positions):
            dist = self._distance_2d(pos, threat)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = idx

        if nearest_idx is not None and nearest_dist < 15.0:
            if roe == "weapons_free":
                return MilitaryEnvironment.ACTION_ENGAGE
            return MilitaryEnvironment.ACTION_TURN_RIGHT

        if nearest_idx is not None and nearest_dist < 30.0:
            return MilitaryEnvironment.ACTION_TURN_LEFT

        dx = waypoint[0] - pos[0]
        dy = waypoint[1] - pos[1]
        target_heading = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
        delta = ((target_heading - heading + 540.0) % 360.0) - 180.0
        if abs(delta) > 12.0:
            return (
                MilitaryEnvironment.ACTION_TURN_LEFT
                if delta > 0
                else MilitaryEnvironment.ACTION_TURN_RIGHT
            )
        if speed < 8.0:
            return MilitaryEnvironment.ACTION_ACCELERATE
        return MilitaryEnvironment.ACTION_MOVE_FORWARD


class RLAgentManager:
    """Manages tactical RL agents with automatic backend selection."""

    def __init__(self, backend: str = "auto") -> None:
        self.registry = PolicyRegistry()
        self.reward_config = RewardConfig()
        self.agents: Dict[str, _ManagedAgent] = {}
        self._backend_libs: Dict[str, Any] = {}
        self.backend_name = self._select_backend(backend)

    def _select_backend(self, backend: str) -> str:
        requested = (backend or "auto").lower().strip()
        if requested not in {"auto", "rllib", "sb3", "builtin", "decision_engine"}:
            requested = "auto"

        def _try_rllib() -> bool:
            try:
                import ray  # type: ignore
                from ray import tune  # type: ignore

                self._backend_libs["ray"] = ray
                self._backend_libs["tune"] = tune
                return True
            except Exception:
                return False

        def _try_sb3() -> bool:
            try:
                import stable_baselines3 as sb3  # type: ignore

                self._backend_libs["sb3"] = sb3
                return True
            except Exception:
                return False

        def _try_decision_engine() -> bool:
            return ProbabilisticDecisionEngine is not None

        if requested == "rllib":
            return "rllib" if _try_rllib() else "builtin"
        if requested == "sb3":
            return "sb3" if _try_sb3() else "builtin"
        if requested == "builtin":
            return "builtin"
        if requested == "decision_engine":
            return "decision_engine" if _try_decision_engine() else "builtin"
        if _try_rllib():
            return "rllib"
        if _try_sb3():
            return "sb3"
        return "builtin"

    def create_agent(self, env: Any, algorithm: str = "PPO", config: Optional[Dict[str, Any]] = None) -> str:
        """Create an RL agent and return its unique ID."""
        if env is None:
            raise ValueError("env is required")
        agent_id = f"agent-{uuid.uuid4().hex[:12]}"
        algo = (algorithm or "PPO").upper()
        cfg = config or {}
        model = None
        if self.backend_name == "builtin":
            model = _BuiltinPolicy(env, algorithm=algo)
        elif self.backend_name == "decision_engine":
            if ProbabilisticDecisionEngine is None:
                model = _BuiltinPolicy(env, algorithm=algo)
            else:
                model = ProbabilisticDecisionEngine()
        elif self.backend_name == "sb3":
            sb3 = self._backend_libs["sb3"]
            if algo == "SAC":
                model = sb3.SAC("MlpPolicy", env, verbose=0, **cfg)
            else:
                model = sb3.PPO("MlpPolicy", env, verbose=0, **cfg)
        else:
            # RLlib trainer handle will be initialized during training.
            model = {"algorithm": algo, "config": cfg}

        self.agents[agent_id] = _ManagedAgent(
            agent_id=agent_id,
            env=env,
            algorithm=algo,
            backend=self.backend_name,
            model=model,
        )
        return agent_id

    def train(
        self,
        agent_id: str,
        n_steps: int = 10000,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Train an agent and return summarized metrics."""
        managed = self.agents.get(agent_id)
        if managed is None:
            raise KeyError(f"unknown agent_id: {agent_id}")
        if n_steps <= 0:
            raise ValueError("n_steps must be > 0")

        metrics: Dict[str, Any]
        if self.backend_name == "sb3":
            model = managed.model
            model.learn(total_timesteps=n_steps)
            managed.trained_steps += n_steps
            eval_stats = self.evaluate(agent_id, n_episodes=5)
            metrics = {
                "mean_reward": eval_stats["mean_reward"],
                "episodes": eval_stats["episodes"],
                "steps": managed.trained_steps,
                "backend": "sb3",
            }
        elif self.backend_name == "rllib":
            ray = self._backend_libs["ray"]
            tune = self._backend_libs["tune"]
            algo = managed.algorithm if managed.algorithm in {"PPO", "SAC"} else "PPO"
            config = {
                "env": lambda _: managed.env,
                "framework": "torch",
                "num_workers": 0,
            }
            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True, include_dashboard=False, local_mode=True)
            analysis = tune.run(
                algo,
                stop={"timesteps_total": n_steps},
                config=config,
                verbose=0,
            )
            best_trial = analysis.get_best_trial(metric="episode_reward_mean", mode="max", scope="all")
            mean_reward = 0.0
            if best_trial is not None and best_trial.last_result:
                mean_reward = float(best_trial.last_result.get("episode_reward_mean", 0.0))
            managed.trained_steps += n_steps
            metrics = {
                "mean_reward": mean_reward,
                "episodes": int(best_trial.last_result.get("episodes_total", 0)) if best_trial else 0,
                "steps": managed.trained_steps,
                "backend": "rllib",
            }
        else:
            metrics = self._train_builtin(managed, n_steps=n_steps, callback=callback)

        managed.training_metrics = dict(metrics)
        if callback:
            callback(metrics)
        return metrics

    def _train_builtin(
        self,
        managed: _ManagedAgent,
        n_steps: int,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        env = managed.env
        policy = managed.model
        episodes = max(1, n_steps // max(1, getattr(env, "max_steps", 200)))
        episode_rewards: List[float] = []
        consumed_steps = 0
        for ep in range(episodes):
            obs, _ = env.reset()
            done = False
            truncated = False
            total_reward = 0.0
            while not done and not truncated and consumed_steps < n_steps:
                action = policy.predict(obs)
                obs, reward, done, truncated, _ = env.step(action)
                total_reward += float(reward)
                consumed_steps += 1
            episode_rewards.append(total_reward)
            if callback:
                callback({"episode": ep + 1, "reward": total_reward})
            if consumed_steps >= n_steps:
                break
        managed.trained_steps += consumed_steps
        managed.episodes += len(episode_rewards)
        mean_reward = sum(episode_rewards) / max(1, len(episode_rewards))
        return {
            "mean_reward": mean_reward,
            "episodes": len(episode_rewards),
            "steps": managed.trained_steps,
            "backend": "builtin",
            "note": "[BUILTIN] Rule-based fallback — install ray or stable-baselines3 for trained policies",
        }

    def predict(self, agent_id: str, observation: Dict[str, Any]) -> int:
        """Run policy inference for one observation."""
        managed = self.agents.get(agent_id)
        if managed is None:
            raise KeyError(f"unknown agent_id: {agent_id}")

        if self.backend_name == "sb3":
            action, _ = managed.model.predict(observation, deterministic=True)
            return int(action)
        if self.backend_name in {"builtin", "decision_engine"}:
            return int(managed.model.predict(observation))
        # RLlib fallback prediction path if trainer unavailable.
        if isinstance(managed.model, dict):
            builtin = _BuiltinPolicy(managed.env, managed.algorithm)
            return int(builtin.predict(observation))
        try:
            action = managed.model.compute_single_action(observation)
            return int(action)
        except Exception:
            builtin = _BuiltinPolicy(managed.env, managed.algorithm)
            return int(builtin.predict(observation))

    def save(self, agent_id: str, name: str) -> None:
        """Persist an agent policy using the registry."""
        managed = self.agents.get(agent_id)
        if managed is None:
            raise KeyError(f"unknown agent_id: {agent_id}")

        metadata = {
            "training_env": managed.env.__class__.__name__,
            "reward_config": asdict(self.reward_config),
            "steps_trained": managed.trained_steps,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "performance_metrics": dict(managed.training_metrics),
            "backend": managed.backend,
            "algorithm": managed.algorithm,
        }
        self.registry.save_policy(name, managed.model, metadata)
        managed.loaded_policy_name = name

    def load(self, name: str) -> str:
        """Load a policy from disk and register as an active agent."""
        policy_obj, metadata = self.registry.load_policy(name)
        env_name = str(metadata.get("training_env", "MilitaryEnvironment"))
        env = MilitaryEnvironment() if env_name == "MilitaryEnvironment" else MilitaryEnvironment()
        agent_id = self.create_agent(
            env=env,
            algorithm=str(metadata.get("algorithm", "PPO")),
            config=None,
        )
        managed = self.agents[agent_id]
        managed.model = policy_obj
        managed.trained_steps = int(metadata.get("steps_trained", 0))
        managed.training_metrics = dict(metadata.get("performance_metrics", {}))
        managed.loaded_policy_name = name
        return agent_id

    def list_agents(self) -> List[Dict[str, Any]]:
        """List active in-memory RL agents."""
        result: List[Dict[str, Any]] = []
        for agent in self.agents.values():
            result.append(
                {
                    "agent_id": agent.agent_id,
                    "backend": agent.backend,
                    "env": agent.env.__class__.__name__,
                    "algorithm": agent.algorithm,
                    "trained_steps": agent.trained_steps,
                    "episodes": agent.episodes,
                    "loaded_policy_name": agent.loaded_policy_name,
                }
            )
        return result

    def evaluate(self, agent_id: str, n_episodes: int = 10) -> Dict[str, Any]:
        """Evaluate a policy and return episode reward statistics."""
        managed = self.agents.get(agent_id)
        if managed is None:
            raise KeyError(f"unknown agent_id: {agent_id}")
        if n_episodes <= 0:
            raise ValueError("n_episodes must be > 0")

        rewards: List[float] = []
        env = managed.env
        for _ in range(n_episodes):
            obs, _ = env.reset()
            done = False
            truncated = False
            total_reward = 0.0
            while not done and not truncated:
                action = self.predict(agent_id, obs)
                obs, reward, done, truncated, _ = env.step(action)
                total_reward += float(reward)
            rewards.append(total_reward)

        mean_reward = sum(rewards) / len(rewards)
        variance = sum((r - mean_reward) ** 2 for r in rewards) / len(rewards)
        return {
            "mean_reward": mean_reward,
            "std_reward": math.sqrt(variance),
            "episodes": n_episodes,
            "backend": self.backend_name,
        }

    def health_check(self) -> Dict[str, Any]:
        """Return subsystem health snapshot for API liveness checks."""
        return {
            "backend": self.backend_name,
            "backend_available": self.backend_name in {"rllib", "sb3", "builtin", "decision_engine"},
            "active_agents": len(self.agents),
            "agents": self.list_agents(),
            "policies_on_disk": self.registry.list_policies(),
        }
