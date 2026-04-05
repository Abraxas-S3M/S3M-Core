"""
S3M Domain Randomization Engine
===============================
Generates diverse simulated conditions to harden models against
real-world uncertainty in contested tactical environments.
"""

from __future__ import annotations

import math
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

try:
    import numpy as np

    NP_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    np = None
    NP_AVAILABLE = False


class RandomizationConfig(BaseModel):
    """Configuration for domain randomization."""

    sensor_noise_std: Tuple[float, float] = (0.01, 0.15)
    sensor_dropout_rate: Tuple[float, float] = (0.0, 0.2)
    position_jitter_m: Tuple[float, float] = (0.0, 5.0)
    timing_offset_ms: Tuple[float, float] = (0.0, 50.0)
    scale_factor: Tuple[float, float] = (0.8, 1.2)
    weather_conditions: List[str] = Field(
        default_factory=lambda: ["clear", "fog", "rain", "dust", "night"]
    )
    terrain_types: List[str] = Field(
        default_factory=lambda: ["desert", "urban", "maritime", "mountain", "forest"]
    )
    adversarial_prob: float = Field(default=0.1, ge=0.0, le=1.0)


class RandomizedSample(BaseModel):
    """A sample after domain randomization has been applied."""

    sample_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    original_data: Dict[str, Any] = Field(default_factory=dict)
    randomized_data: Dict[str, Any] = Field(default_factory=dict)
    applied_randomizations: List[str] = Field(default_factory=list)
    weather: str = "clear"
    terrain: str = "desert"
    noise_level: float = 0.0


class DomainRandomizer:
    """
    Apply configurable randomization to simulation samples.

    This improves robustness by exposing models to plausible sensor,
    environmental, and timing variation before edge deployment.
    """

    def __init__(
        self,
        config: Optional[RandomizationConfig] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.config = config or RandomizationConfig()
        self._rng = random.Random(seed)
        self._np_rng = np.random.RandomState(seed) if NP_AVAILABLE else None
        self._sample_count = 0

    def randomize(self, data: Dict[str, Any]) -> RandomizedSample:
        """Apply configured randomization pipeline to one sample."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        self._sample_count += 1

        randomized: Dict[str, Any] = dict(data)
        applied: List[str] = []

        noise_std = self._rng.uniform(*self.config.sensor_noise_std)
        randomized = self._add_sensor_noise(randomized, noise_std)
        applied.append(f"sensor_noise(std={noise_std:.4f})")

        dropout_rate = self._rng.uniform(*self.config.sensor_dropout_rate)
        if dropout_rate > 0.0:
            randomized = self._apply_dropout(randomized, dropout_rate)
            applied.append(f"sensor_dropout(rate={dropout_rate:.4f})")

        jitter = self._rng.uniform(*self.config.position_jitter_m)
        if jitter > 0.0:
            randomized = self._add_position_jitter(randomized, jitter)
            applied.append(f"position_jitter(m={jitter:.2f})")

        offset = self._rng.uniform(*self.config.timing_offset_ms)
        if offset > 0.0:
            randomized["timing_offset_ms"] = offset
            applied.append(f"timing_offset(ms={offset:.1f})")

        weather = self._rng.choice(self.config.weather_conditions)
        terrain = self._rng.choice(self.config.terrain_types)
        randomized["weather"] = weather
        randomized["terrain"] = terrain
        applied.append(f"weather={weather}")
        applied.append(f"terrain={terrain}")

        if self._rng.random() < self.config.adversarial_prob:
            randomized = self._adversarial_perturb(randomized)
            applied.append("adversarial_perturbation")

        return RandomizedSample(
            original_data=data,
            randomized_data=randomized,
            applied_randomizations=applied,
            weather=weather,
            terrain=terrain,
            noise_level=noise_std,
        )

    def _add_sensor_noise(self, data: Dict[str, Any], std: float) -> Dict[str, Any]:
        """Inject Gaussian-like noise into numeric channels."""
        result: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, (int, float)):
                result[key] = float(value) + self._noise(std, abs(float(value) + 1e-6))
            elif isinstance(value, list) and all(isinstance(v, (int, float)) for v in value):
                result[key] = [float(v) + self._noise(std, abs(float(v) + 1e-6)) for v in value]
            else:
                result[key] = value
        return result

    def _apply_dropout(self, data: Dict[str, Any], rate: float) -> Dict[str, Any]:
        """Randomly zero selected numeric channels to emulate sensor loss."""
        result: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, (int, float)) and self._rng.random() < rate:
                result[key] = 0.0
            else:
                result[key] = value
        return result

    def _add_position_jitter(self, data: Dict[str, Any], jitter_m: float) -> Dict[str, Any]:
        """Apply positional uncertainty for navigation and targeting stress tests."""
        result = dict(data)
        for key in ("x", "y", "z", "lat", "lon", "altitude"):
            value = result.get(key)
            if isinstance(value, (int, float)):
                result[key] = float(value) + self._noise(1.0, jitter_m)
        return result

    def _adversarial_perturb(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply bounded adversarial scaling to numeric channels."""
        result = dict(data)
        for key, value in list(result.items()):
            if isinstance(value, (int, float)) and self._rng.random() < 0.3:
                result[key] = float(value) * self._rng.uniform(0.5, 2.0)
        return result

    def get_stats(self) -> Dict[str, int]:
        return {"total_samples_randomized": self._sample_count}

    def _noise(self, std: float, scale: float) -> float:
        magnitude = max(1e-6, abs(scale) * max(0.0, std))
        if self._np_rng is not None:
            value = float(self._np_rng.normal(0.0, magnitude))
        else:
            value = self._rng.gauss(0.0, magnitude)
        if not math.isfinite(value):
            return 0.0
        return value
