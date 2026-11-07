"""Le Chonk deployment profile identifiers and metadata."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


class DeploymentProfile(str, Enum):
    FP8_GPU = "fp8_gpu"
    NVFP4_BLACKWELL_GPU = "nvfp4_blackwell_gpu"
    CPU_GGUF_EXPERIMENTAL = "cpu_gguf_experimental"
    FALLBACK_SMALL_MODEL = "fallback_small_model"


PROFILE_ORDER_GPU = (
    DeploymentProfile.NVFP4_BLACKWELL_GPU,
    DeploymentProfile.FP8_GPU,
    DeploymentProfile.FALLBACK_SMALL_MODEL,
)


def variant_tag_to_profile(tag: str) -> Optional[DeploymentProfile]:
    mapping = {
        "fp8_gpu": DeploymentProfile.FP8_GPU,
        "nvfp4_blackwell_gpu": DeploymentProfile.NVFP4_BLACKWELL_GPU,
        "cpu_gguf": DeploymentProfile.CPU_GGUF_EXPERIMENTAL,
    }
    return mapping.get(tag.strip())


def profiles_from_manifest(manifest_doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    variants = manifest_doc.get("variants") or []
    profiles: List[Dict[str, Any]] = []
    if not isinstance(variants, list):
        return profiles
    for item in variants:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "")
        profile = variant_tag_to_profile(tag)
        if profile is None:
            continue
        profiles.append(
            {
                "profile": profile.value,
                "tag": tag,
                "status": str(item.get("status") or "quarantine"),
                "runtime": str(item.get("runtime") or ""),
                "device": str(item.get("device") or ""),
                "source_revision": str(item.get("source_revision") or ""),
            }
        )
    profiles.append(
        {
            "profile": DeploymentProfile.FALLBACK_SMALL_MODEL.value,
            "tag": "fallback_small_model",
            "status": "active",
            "runtime": "gguf",
            "device": "cpu",
            "source_revision": "",
        }
    )
    return profiles
