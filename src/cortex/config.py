"""Cortex tier-aware configuration loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

from src.cortex.policy_gate import PolicyGateConfig


@dataclass(frozen=True, slots=True)
class TierProfile:
    """Hardware and quantization profile for one deployment tier."""

    name: str
    offline_required: bool
    quantization: str
    max_gpus: int = 1


@dataclass(frozen=True, slots=True)
class CortexConfig:
    """Root Cortex settings."""

    deployment_profile: str
    policy_gate: PolicyGateConfig
    tiers: Dict[str, TierProfile] = field(default_factory=dict)


def load_cortex_config(path: str | Path) -> CortexConfig:
    """Load configs/cortex.yaml with strict validation."""
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("cortex config must be a mapping")

    gate_raw = raw.get("policy_gate") or {}
    gate = PolicyGateConfig(
        enabled=bool(gate_raw.get("enabled", True)),
        production_mode=bool(gate_raw.get("production_mode", False)),
        evaluation_timeout_s=float(gate_raw.get("evaluation_timeout_s", 1.0)),
    )

    tiers: Dict[str, TierProfile] = {}
    for name, tier in (raw.get("tiers") or {}).items():
        if not isinstance(tier, dict):
            continue
        tiers[str(name)] = TierProfile(
            name=str(name),
            offline_required=bool(tier.get("offline_required", True)),
            quantization=str(tier.get("quantization", "int8")),
            max_gpus=int(tier.get("max_gpus", 1)),
        )

    return CortexConfig(
        deployment_profile=str(raw.get("deployment_profile", "edge")),
        policy_gate=gate,
        tiers=tiers,
    )
