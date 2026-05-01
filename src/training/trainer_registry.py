"""Track/scenario trainer configuration registry for S3M-Engine.

Military/tactical context:
Centralized trainer routing policy prevents sensitive mission tracks from
accidentally using unsafe hyperparameters or the wrong GPU job template.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


_REQUIRED_CONFIG_FIELDS = (
    "trainer_type",
    "base_model",
    "learning_rate",
    "batch_size",
    "max_epochs",
    "warmup_steps",
    "gradient_accumulation",
    "mixed_precision",
    "runpod_template",
)

_VALID_TRAINER_TYPES = {"causal_lm", "seq2seq", "classification"}


class TrainerRegistry:
    """Resolve trainer configs for track/scenario routing intents."""

    def __init__(self, config_path: Path = Path("configs/tracks.yaml")) -> None:
        self._config_path = Path(config_path)
        self._registry: dict[tuple[str, str], dict[str, Any]] = {}
        self._seed_default_assignments()
        self._load_from_yaml_if_present()

    def get_trainer_config(self, track: str, scenario: str) -> dict[str, Any]:
        """Return the validated trainer configuration for track/scenario."""
        track_key = self._normalize_route_key(track, "track")
        scenario_key = self._normalize_route_key(scenario, "scenario")

        exact = self._registry.get((track_key, scenario_key))
        if exact is not None:
            return deepcopy(exact)

        wildcard = self._registry.get((track_key, "*"))
        if wildcard is not None:
            return deepcopy(wildcard)

        raise KeyError(f"No trainer configuration found for '{track_key}/{scenario_key}'")

    def list_trainers(self) -> list[dict[str, Any]]:
        """List all registered trainer routes as plain dictionaries."""
        trainers: list[dict[str, Any]] = []
        for (track, scenario), config in sorted(self._registry.items(), key=lambda item: item[0]):
            trainers.append(
                {
                    "track": track,
                    "scenario": scenario,
                    **deepcopy(config),
                }
            )
        return trainers

    def register_trainer(self, track: str, scenario: str, config: dict[str, Any]) -> None:
        """Register or overwrite one trainer route configuration."""
        if not isinstance(config, dict):
            raise TypeError("config must be a dictionary")

        track_key = self._normalize_route_key(track, "track")
        scenario_key = self._normalize_route_key(scenario, "scenario")
        base = self._default_config_for_track(track_key)

        candidate = dict(base)
        candidate.update(config)
        normalized = self._normalize_and_validate_config(candidate)
        self._registry[(track_key, scenario_key)] = normalized

    def _seed_default_assignments(self) -> None:
        """Install baseline defaults required by the initial routing policy."""
        self.register_trainer(
            "general",
            "*",
            {
                "trainer_type": "causal_lm",
                "base_model": "models/quantized/general-causal-lm",
                "learning_rate": 2e-5,
                "batch_size": 8,
                "max_epochs": 4,
                "warmup_steps": 100,
                "gradient_accumulation": 1,
                "mixed_precision": True,
                "runpod_template": "runpod-general-causal-lm",
            },
        )
        self.register_trainer(
            "cop_intel",
            "*",
            {
                "trainer_type": "causal_lm",
                "base_model": "models/quantized/cop-intel-causal-lm",
                "learning_rate": 1e-5,
                "batch_size": 4,
                "max_epochs": 5,
                "warmup_steps": 200,
                "gradient_accumulation": 2,
                "mixed_precision": False,
                "runpod_template": "runpod-cop-intel-secure",
            },
        )
        self.register_trainer(
            "saudi_mod",
            "*",
            {
                "trainer_type": "causal_lm",
                "base_model": "models/quantized/saudi-mod-causal-lm",
                "learning_rate": 2e-5,
                "batch_size": 4,
                "max_epochs": 4,
                "warmup_steps": 150,
                "gradient_accumulation": 2,
                "mixed_precision": True,
                "runpod_template": "runpod-saudi-mod-causal-lm",
            },
        )
        self.register_trainer(
            "operations",
            "*",
            {
                "trainer_type": "causal_lm",
                "base_model": "models/quantized/operations-causal-lm",
                "learning_rate": 2e-5,
                "batch_size": 8,
                "max_epochs": 4,
                "warmup_steps": 100,
                "gradient_accumulation": 1,
                "mixed_precision": True,
                "runpod_template": "runpod-operations-causal-lm",
            },
        )

    def _load_from_yaml_if_present(self) -> None:
        if not self._config_path.exists():
            return

        raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("tracks.yaml must contain a top-level mapping")

        trainers_payload = raw.get("trainers")
        if isinstance(trainers_payload, list):
            for item in trainers_payload:
                if not isinstance(item, dict):
                    continue
                track = item.get("track")
                scenario = item.get("scenario", "*")
                config = item.get("config")
                if isinstance(track, str) and isinstance(scenario, str) and isinstance(config, dict):
                    self.register_trainer(track, scenario, config)
            return

        tracks_payload = raw.get("tracks")
        if isinstance(tracks_payload, dict):
            for track, payload in tracks_payload.items():
                if not isinstance(track, str) or not isinstance(payload, dict):
                    continue
                scenarios = payload.get("scenarios")
                if isinstance(scenarios, dict):
                    for scenario, config in scenarios.items():
                        if isinstance(scenario, str) and isinstance(config, dict):
                            self.register_trainer(track, scenario, config)
                defaults = payload.get("default")
                if isinstance(defaults, dict):
                    self.register_trainer(track, "*", defaults)

    def _default_config_for_track(self, track: str) -> dict[str, Any]:
        seeded = self._registry.get((track, "*"))
        if seeded is not None:
            return deepcopy(seeded)
        # Tactical fallback keeps unknown tracks in a conservative baseline.
        return {
            "trainer_type": "causal_lm",
            "base_model": "models/quantized/default-causal-lm",
            "learning_rate": 2e-5,
            "batch_size": 8,
            "max_epochs": 4,
            "warmup_steps": 100,
            "gradient_accumulation": 1,
            "mixed_precision": True,
            "runpod_template": "runpod-default-causal-lm",
        }

    @staticmethod
    def _normalize_route_key(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"{field_name} cannot be empty")
        return normalized

    @staticmethod
    def _normalize_and_validate_config(config: dict[str, Any]) -> dict[str, Any]:
        missing = [field for field in _REQUIRED_CONFIG_FIELDS if field not in config]
        if missing:
            raise ValueError(f"config missing required fields: {', '.join(missing)}")

        trainer_type = str(config["trainer_type"]).strip().lower()
        if trainer_type not in _VALID_TRAINER_TYPES:
            raise ValueError(f"trainer_type must be one of: {sorted(_VALID_TRAINER_TYPES)}")

        base_model = str(config["base_model"]).strip()
        runpod_template = str(config["runpod_template"]).strip()
        if not base_model:
            raise ValueError("base_model cannot be empty")
        if not runpod_template:
            raise ValueError("runpod_template cannot be empty")

        learning_rate = float(config["learning_rate"])
        batch_size = int(config["batch_size"])
        max_epochs = int(config["max_epochs"])
        warmup_steps = int(config["warmup_steps"])
        gradient_accumulation = int(config["gradient_accumulation"])
        mixed_precision = bool(config["mixed_precision"])

        if learning_rate <= 0:
            raise ValueError("learning_rate must be > 0")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if max_epochs <= 0:
            raise ValueError("max_epochs must be > 0")
        if warmup_steps < 0:
            raise ValueError("warmup_steps must be >= 0")
        if gradient_accumulation <= 0:
            raise ValueError("gradient_accumulation must be > 0")

        return {
            "trainer_type": trainer_type,
            "base_model": base_model,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "max_epochs": max_epochs,
            "warmup_steps": warmup_steps,
            "gradient_accumulation": gradient_accumulation,
            "mixed_precision": mixed_precision,
            "runpod_template": runpod_template,
        }
