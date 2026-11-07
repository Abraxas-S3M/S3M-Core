"""Hardware and resource probes for Le Chonk deployment profile selection."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class HardwareSnapshot:
    """Point-in-time host capabilities — informative only, not a production GPU probe."""

    platform_system: str
    cpu_count: int
    ram_total_bytes: Optional[int]
    ram_available_bytes: Optional[int]
    nvidia_smi_present: bool
    cuda_visible_devices: str
    gpu_product_names: tuple[str, ...] = field(default_factory=tuple)
    blackwell_like: bool = False

    def summary(self) -> str:
        gpus = ", ".join(self.gpu_product_names) if self.gpu_product_names else "none_detected"
        return (
            f"cpus={self.cpu_count} nvidia_smi={self.nvidia_smi_present} "
            f"gpus=[{gpus}] blackwell_hint={self.blackwell_like}"
        )


def _read_meminfo_available() -> tuple[Optional[int], Optional[int]]:
    path = "/proc/meminfo"
    if not os.path.isfile(path):
        return None, None
    total: Optional[int] = None
    available: Optional[int] = None
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
    except (OSError, ValueError):
        return None, None
    return total, available


def _probe_nvidia_smi() -> tuple[bool, List[str]]:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return False, []
    try:
        import subprocess

        proc = subprocess.run(
            [binary, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True, []
    names = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    return proc.returncode == 0, names


def collect_hardware_snapshot() -> HardwareSnapshot:
    total, available = _read_meminfo_available()
    smi_ok, gpu_names = _probe_nvidia_smi()
    blackwell = any("blackwell" in n.lower() or "b200" in n.lower() or "b100" in n.lower() for n in gpu_names)
    return HardwareSnapshot(
        platform_system=platform.system(),
        cpu_count=os.cpu_count() or 1,
        ram_total_bytes=total,
        ram_available_bytes=available,
        nvidia_smi_present=smi_ok and bool(shutil.which("nvidia-smi")),
        cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES", ""),
        gpu_product_names=tuple(gpu_names),
        blackwell_like=blackwell,
    )


def minimum_vram_bytes_for_tag(tag: str) -> Optional[int]:
    """Conservative staging thresholds — not validated on real 1T loads."""
    thresholds = {
        "fp8_gpu": 400 * 1024**3,
        "nvfp4_blackwell_gpu": 200 * 1024**3,
        "fallback_small_model": 8 * 1024**3,
    }
    return thresholds.get(tag)
