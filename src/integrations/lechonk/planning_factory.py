"""Construct LeChonkPlanningBackend from engines.yaml without exposing secrets."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml

from src.cortex.model_admission import engine_config
from src.integrations.lechonk.planning_backend import LeChonkPlanningBackend
from src.llm_core.backends.vllm_backend import VllmBackend


def _vllm_settings(engines_path: str = "configs/engines.yaml") -> Dict[str, Any]:
    cfg = engine_config("mistral_large_4", engines_path)
    block = cfg.get("lechonk") or {}
    vllm = block.get("private_vllm") if isinstance(block, dict) else {}
    if not isinstance(vllm, dict):
        vllm = {}
    base_url = os.environ.get(str(vllm.get("base_url_env") or "S3M_LECHONK_VLLM_BASE_URL"), "").strip()
    if not base_url:
        base_url = os.environ.get("S3M_VLLM_BASE_URL", "").strip()
    return {
        "base_url": base_url,
        "model_name": str(vllm.get("model_name") or "mistral-large-4"),
        "max_concurrent_requests": int(vllm.get("max_concurrent_requests") or 2),
        "request_timeout_s": float(vllm.get("request_timeout_s") or 120.0),
        "max_tokens": int(cfg.get("max_tokens") or 1024),
        "lab_mode": True,
        "internal_hostnames": frozenset(),
    }


def build_planning_backend(
    *,
    engines_path: str = "configs/engines.yaml",
    backend_override: Optional[LeChonkPlanningBackend] = None,
) -> Optional[LeChonkPlanningBackend]:
    if backend_override is not None:
        return backend_override
    settings = _vllm_settings(engines_path)
    if not settings.get("base_url"):
        return None
    return LeChonkPlanningBackend.from_vllm_config(str(settings["model_name"]), settings)
