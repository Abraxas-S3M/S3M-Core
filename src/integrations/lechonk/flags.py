"""Feature flag and rollback helpers for Le Chonk planning-engine staging."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

LECHONK_FEATURE_FLAG = "S3M_LECHONK_ENABLED"
_DEFAULT_MANIFEST = Path("configs/model_manifests/mistral_large_4.yaml")
BACKING_ENGINE_ID = "mistral_large_4"
LEGACY_ROLLBACK_ENGINE_ID = "mistral"


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def load_lechonk_manifest(manifest_path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(manifest_path or _DEFAULT_MANIFEST)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def manifest_feature_default() -> bool:
    doc = load_lechonk_manifest()
    flag = doc.get("feature_flag") or {}
    if isinstance(flag, dict):
        return bool(flag.get("default", False))
    return False


def execution_allowed_by_manifest() -> bool:
    """True only when manifest explicitly allows model execution (never in quarantine)."""
    doc = load_lechonk_manifest()
    security = doc.get("security") or {}
    if isinstance(security, dict) and security.get("allow_model_execution") is True:
        return bool(doc.get("execution_enabled", False))
    return False


def lechonk_enabled(*, manifest_path: Optional[str] = None) -> bool:
    """
    Le Chonk routing is disabled unless the env flag is on AND manifest permits execution.

    Production posture: default false; quarantined manifest keeps execution off.
    """
    doc = load_lechonk_manifest(manifest_path) if manifest_path else load_lechonk_manifest()
    default = False
    flag = doc.get("feature_flag") or {}
    if isinstance(flag, dict):
        default = bool(flag.get("default", False))
    if not _env_truthy(LECHONK_FEATURE_FLAG, default=default):
        return False
    return execution_allowed_by_manifest()


def rollback_planning_binding() -> str:
    doc = load_lechonk_manifest()
    rollback = doc.get("rollback") or {}
    if isinstance(rollback, dict):
        binding = str(rollback.get("planning_engine_binding") or "").strip()
        if binding:
            return binding
    return LEGACY_ROLLBACK_ENGINE_ID
