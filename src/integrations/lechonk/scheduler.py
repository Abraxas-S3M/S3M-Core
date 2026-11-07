"""Profile auto-selection for Le Chonk — never silently run 1T on unsupported CPU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from src.integrations.lechonk.deployment_profiles import (
    PROFILE_ORDER_GPU,
    DeploymentProfile,
    profiles_from_manifest,
)
from src.integrations.lechonk.flags import load_lechonk_manifest
from src.integrations.lechonk.hardware import HardwareSnapshot, collect_hardware_snapshot, minimum_vram_bytes_for_tag
from src.integrations.lechonk.runtime_compat import RuntimeCompatibilityReport, evaluate_runtime_compatibility


@dataclass(frozen=True)
class ProfileSelection:
    selected: DeploymentProfile
    reasons: List[str]
    rejected: List[str]
    hardware: HardwareSnapshot
    runtime: RuntimeCompatibilityReport

    def uses_lechonk_weights(self) -> bool:
        return self.selected in {
            DeploymentProfile.FP8_GPU,
            DeploymentProfile.NVFP4_BLACKWELL_GPU,
        }


def _variant_status(manifest_doc: Mapping[str, Any], tag: str) -> str:
    for item in manifest_doc.get("variants") or []:
        if isinstance(item, dict) and str(item.get("tag")) == tag:
            return str(item.get("status") or "quarantine").lower()
    return "quarantine"


def select_deployment_profile(
    manifest_doc: Optional[Mapping[str, Any]] = None,
    *,
    hardware: Optional[HardwareSnapshot] = None,
    runtime_report: Optional[RuntimeCompatibilityReport] = None,
    force_fallback: bool = False,
) -> ProfileSelection:
    doc = dict(manifest_doc or load_lechonk_manifest())
    hw = hardware or collect_hardware_snapshot()
    runtime = runtime_report or evaluate_runtime_compatibility()
    reasons: List[str] = []
    rejected: List[str] = []

    if force_fallback or not runtime.ready_for_inference:
        rejected.append("runtime_not_verified")
        return ProfileSelection(
            selected=DeploymentProfile.FALLBACK_SMALL_MODEL,
            reasons=["fallback:runtime_or_flag"],
            rejected=rejected,
            hardware=hw,
            runtime=runtime,
        )

    for profile in PROFILE_ORDER_GPU:
        if profile == DeploymentProfile.FALLBACK_SMALL_MODEL:
            continue
        tag = profile.value
        if profile == DeploymentProfile.NVFP4_BLACKWELL_GPU:
            tag = "nvfp4_blackwell_gpu"
        status = _variant_status(doc, tag)
        if status in {"quarantine", "unavailable", "not_selected"}:
            rejected.append(f"{tag}:status_{status}")
            continue
        if profile == DeploymentProfile.NVFP4_BLACKWELL_GPU and not hw.blackwell_like:
            rejected.append("nvfp4:blackwell_not_detected")
            continue
        if not hw.nvidia_smi_present:
            rejected.append(f"{tag}:no_gpu_probe")
            continue
        min_vram = minimum_vram_bytes_for_tag(tag)
        if min_vram and hw.ram_total_bytes and hw.ram_total_bytes < min_vram:
            rejected.append(f"{tag}:insufficient_host_ram_for_staging_threshold")
            continue
        reasons.append(f"selected:{tag}")
        return ProfileSelection(
            selected=profile,
            reasons=reasons,
            rejected=rejected,
            hardware=hw,
            runtime=runtime,
        )

    reasons.append("fallback:no_eligible_gpu_profile")
    return ProfileSelection(
        selected=DeploymentProfile.FALLBACK_SMALL_MODEL,
        reasons=reasons,
        rejected=rejected,
        hardware=hw,
        runtime=runtime,
    )


def list_configured_profiles(manifest_doc: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    return profiles_from_manifest(dict(manifest_doc or load_lechonk_manifest()))
