"""vLLM / runtime compatibility checks — never claim success without a smoke test."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class RuntimeCompatibilityReport:
    runtime: str
    pinned_build: str
    architecture_support: str
    smoke_test_passed: bool
    notes: List[str]

    @property
    def ready_for_inference(self) -> bool:
        return self.smoke_test_passed and self.architecture_support == "verified"


def pinned_vllm_build() -> str:
    return os.environ.get("S3M_LECHONK_VLLM_BUILD", "").strip() or "unpinned"


def parse_vllm_version_output(text: str) -> Optional[str]:
    match = re.search(r"vllm[/\s]+([\d.]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def evaluate_runtime_compatibility(
    *,
    lab_smoke_test_passed: Optional[bool] = None,
    pinned_build: Optional[str] = None,
) -> RuntimeCompatibilityReport:
    """
    Staging report only. Production must set lab_smoke_test_passed after a real load test.
    """
    build = pinned_build or pinned_vllm_build()
    smoke = False if lab_smoke_test_passed is None else bool(lab_smoke_test_passed)
    arch = "unverified"
    notes = [
        "Mistral Large 4 MoE support must be validated against the pinned vLLM build on target GPUs.",
        "No generic vLLM version is assumed compatible until smoke_test_passed is true.",
    ]
    if smoke:
        arch = "verified"
        notes.append("Smoke test flag set by operator — not fabricated by default.")
    return RuntimeCompatibilityReport(
        runtime="vllm",
        pinned_build=build,
        architecture_support=arch,
        smoke_test_passed=smoke,
        notes=notes,
    )
