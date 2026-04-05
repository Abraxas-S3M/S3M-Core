"""
S3M Prioritized Experience Replay Buffer.

Military/tactical context:
High-error outcomes are replayed more often so scarce mission data from
unexpected events has higher training impact than routine observations.
"""

from __future__ import annotations

import base64
import math
import pickle
import random
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class Experience(BaseModel):
    """Single transition sample for replay."""

    experience_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    state: Dict[str, Any] = Field(default_factory=dict)
    action: str = ""
    reward: float = 0.0
    next_state: Dict[str, Any] = Field(default_factory=dict)
    done: bool = False
    td_error: float = Field(default=1.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PrioritizedReplayBuffer:
    """
    Prioritized replay with proportional sampling.

    Priority = (abs(td_error) + epsilon) ** alpha
    """

    def __init__(
        self,
        capacity: int = 50000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
        epsilon: float = 0.01,
        seed: Optional[int] = None,
    ) -> None:
        if capacity < 100:
            raise ValueError("capacity must be >= 100")
        if not (0.0 <= alpha <= 1.5):
            raise ValueError("alpha must be between 0.0 and 1.5")
        if not (0.0 <= beta <= 1.0):
            raise ValueError("beta must be between 0.0 and 1.0")

        self._capacity = int(capacity)
        self._alpha = float(alpha)
        self._beta = float(beta)
        self._beta_inc = float(beta_increment)
        self._epsilon = float(epsilon)
        self._rng = random.Random(seed)

        self._buffer: List[Optional[Experience]] = [None] * self._capacity
        self._priorities: List[float] = [0.0] * self._capacity
        self._position = 0
        self._size = 0
        self._max_priority = 1.0
        self._lock = threading.RLock()

    def add(self, experience: Experience) -> None:
        if not isinstance(experience, Experience):
            raise TypeError("experience must be an Experience instance")
        with self._lock:
            priority = max((abs(float(experience.td_error)) + self._epsilon) ** self._alpha, self._epsilon)
            self._buffer[self._position] = experience
            self._priorities[self._position] = float(priority)
            self._max_priority = max(self._max_priority, float(priority))
            self._position = (self._position + 1) % self._capacity
            self._size = min(self._size + 1, self._capacity)

    def sample(self, batch_size: int) -> Tuple[List[Experience], List[float], List[int]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        with self._lock:
            if self._size == 0:
                return [], [], []

            n = min(int(batch_size), self._size)
            active_priorities = self._priorities[: self._size]
            total_priority = float(sum(active_priorities))
            if total_priority <= 0.0:
                total_priority = 1.0
                active_priorities = [1.0] * self._size

            indices: List[int] = []
            for _ in range(n):
                target = self._rng.random() * total_priority
                cumulative = 0.0
                chosen = self._size - 1
                for idx, priority in enumerate(active_priorities):
                    cumulative += priority
                    if cumulative >= target:
                        chosen = idx
                        break
                indices.append(chosen)

            experiences = [self._buffer[idx] for idx in indices]
            if any(exp is None for exp in experiences):
                filtered: List[Tuple[int, Experience]] = [
                    (idx, exp) for idx, exp in zip(indices, experiences) if exp is not None
                ]
                if not filtered:
                    return [], [], []
                indices = [idx for idx, _ in filtered]
                experiences = [exp for _, exp in filtered]

            weights: List[float] = []
            for idx in indices:
                prob = max(active_priorities[idx] / total_priority, 1e-12)
                weight = (prob * self._size) ** (-self._beta)
                weights.append(float(weight))
            max_weight = max(weights) if weights else 1.0
            weights = [w / max_weight for w in weights]

            self._beta = min(1.0, self._beta + self._beta_inc)
            return [exp for exp in experiences if exp is not None], weights, indices

    def update_priorities(self, indices: List[int], td_errors: List[float]) -> None:
        if len(indices) != len(td_errors):
            raise ValueError("indices and td_errors must have equal length")
        with self._lock:
            for idx, td_error in zip(indices, td_errors):
                if 0 <= idx < self._size:
                    priority = max((abs(float(td_error)) + self._epsilon) ** self._alpha, self._epsilon)
                    self._priorities[idx] = float(priority)
                    self._max_priority = max(self._max_priority, float(priority))

    def size(self) -> int:
        with self._lock:
            return self._size

    def export_state(self) -> Dict[str, Any]:
        with self._lock:
            rng_state = base64.b64encode(pickle.dumps(self._rng.getstate())).decode("ascii")
            return {
                "capacity": self._capacity,
                "alpha": self._alpha,
                "beta": self._beta,
                "beta_increment": self._beta_inc,
                "epsilon": self._epsilon,
                "position": self._position,
                "size": self._size,
                "max_priority": self._max_priority,
                "priorities": self._priorities[: self._size],
                "experiences": [
                    self._buffer[idx].model_dump() if self._buffer[idx] is not None else None
                    for idx in range(self._size)
                ],
                "rng_state": rng_state,
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary")
        capacity = int(state.get("capacity", 0))
        if capacity < 100:
            raise ValueError("state.capacity must be >= 100")

        with self._lock:
            self._capacity = capacity
            self._alpha = float(state.get("alpha", self._alpha))
            self._beta = float(state.get("beta", self._beta))
            self._beta_inc = float(state.get("beta_increment", self._beta_inc))
            self._epsilon = float(state.get("epsilon", self._epsilon))
            self._position = int(state.get("position", 0))
            self._size = int(state.get("size", 0))
            self._max_priority = float(state.get("max_priority", 1.0))
            self._buffer = [None] * self._capacity
            self._priorities = [0.0] * self._capacity

            priorities = list(state.get("priorities", []))
            experiences = list(state.get("experiences", []))
            for idx in range(min(self._size, len(priorities), len(experiences))):
                self._priorities[idx] = float(priorities[idx])
                item = experiences[idx]
                if item is not None:
                    self._buffer[idx] = Experience.model_validate(item)

            rng_state_encoded = state.get("rng_state")
            if isinstance(rng_state_encoded, str) and rng_state_encoded:
                try:
                    decoded = base64.b64decode(rng_state_encoded.encode("ascii"))
                    self._rng.setstate(pickle.loads(decoded))
                except Exception:
                    # Keep deterministic fallback if checkpoint RNG cannot be restored.
                    self._rng = random.Random(0)

