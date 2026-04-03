"""
S3M Phase 21 - Hardware capability profiling for denied edge nodes.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
import platform
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple


class HardwareTier(str, Enum):
    """Hardware capability tiers used for tactical runtime policy."""

    CPU_AUSTERE = "cpu_austere"
    CPU_STANDARD = "cpu_standard"
    EDGE_GPU = "edge_gpu"
    VEHICLE_NODE = "vehicle_node"
    FIXED_SITE = "fixed_site"


@dataclass
class NodeProfile:
    """Snapshot of host capabilities used for runtime decisions."""

    tier: HardwareTier
    cpu_cores: int
    cpu_arch: str
    ram_total_gb: float
    ram_available_gb: float
    disk_total_gb: float
    disk_free_gb: float
    gpu_detected: bool
    gpu_name: Optional[str]
    gpu_memory_mb: int
    cuda_available: bool
    thermal_zone_c: Optional[float]
    power_source: str
    active_links: List[str]
    profiled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, object]:
        """Serialize for API/health surfaces."""
        return {
            "tier": self.tier.value,
            "cpu_cores": self.cpu_cores,
            "cpu_arch": self.cpu_arch,
            "ram_total_gb": self.ram_total_gb,
            "ram_available_gb": self.ram_available_gb,
            "disk_total_gb": self.disk_total_gb,
            "disk_free_gb": self.disk_free_gb,
            "gpu_detected": self.gpu_detected,
            "gpu_name": self.gpu_name,
            "gpu_memory_mb": self.gpu_memory_mb,
            "cuda_available": self.cuda_available,
            "thermal_zone_c": self.thermal_zone_c,
            "power_source": self.power_source,
            "active_links": list(self.active_links),
            "profiled_at": self.profiled_at,
        }


class HardwareProfiler:
    """Boot-time capability profiler with conservative fallback behavior."""

    def __init__(self) -> None:
        self.profile: Optional[NodeProfile] = None

    def run(self) -> NodeProfile:
        """Collect probes once and cache result."""
        cpu_cores = self._probe_cpu_cores()
        cpu_arch = self._probe_cpu_arch()
        ram_total_gb, ram_available_gb = self._probe_memory()
        disk_total_gb, disk_free_gb = self._probe_disk()
        gpu_detected, gpu_name, gpu_memory_mb, cuda_available = self._probe_gpu()
        thermal_zone_c = self._probe_thermal_zone()
        power_source = self._probe_power_source()
        active_links = self._probe_active_links()
        tier = self._classify(
            cores=cpu_cores,
            ram_gb=ram_total_gb,
            gpu=gpu_detected,
            thermal=thermal_zone_c,
            power=power_source,
        )
        self.profile = NodeProfile(
            tier=tier,
            cpu_cores=cpu_cores,
            cpu_arch=cpu_arch,
            ram_total_gb=ram_total_gb,
            ram_available_gb=ram_available_gb,
            disk_total_gb=disk_total_gb,
            disk_free_gb=disk_free_gb,
            gpu_detected=gpu_detected,
            gpu_name=gpu_name,
            gpu_memory_mb=gpu_memory_mb,
            cuda_available=cuda_available,
            thermal_zone_c=thermal_zone_c,
            power_source=power_source,
            active_links=active_links,
        )
        return self.profile

    @staticmethod
    def _probe_cpu_cores() -> int:
        try:
            return max(1, int(os.cpu_count() or 1))
        except Exception:
            return 1

    @staticmethod
    def _probe_cpu_arch() -> str:
        try:
            arch = str(platform.machine())
            return arch if arch else "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _probe_memory() -> Tuple[float, float]:
        fallback = (4.0, 2.0)
        try:
            meminfo = Path("/proc/meminfo")
            if not meminfo.exists():
                return fallback
            values: Dict[str, int] = {}
            for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ":" not in line:
                    continue
                key, raw = line.split(":", 1)
                parts = raw.strip().split()
                if not parts:
                    continue
                values[key.strip()] = int(parts[0])
            total_kb = values.get("MemTotal")
            available_kb = values.get("MemAvailable")
            if total_kb is None or available_kb is None:
                return fallback
            total_gb = round(total_kb / (1024.0 * 1024.0), 2)
            available_gb = round(available_kb / (1024.0 * 1024.0), 2)
            return total_gb, available_gb
        except Exception:
            return fallback

    @staticmethod
    def _probe_disk() -> Tuple[float, float]:
        fallback = (32.0, 16.0)
        try:
            usage = shutil.disk_usage("/")
            total_gb = round(usage.total / (1024.0**3), 2)
            free_gb = round(usage.free / (1024.0**3), 2)
            return total_gb, free_gb
        except Exception:
            return fallback

    @staticmethod
    def _probe_gpu() -> Tuple[bool, Optional[str], int, bool]:
        # CPU-first runtime: GPU detection is best-effort and never required.
        try:
            import torch  # type: ignore

            if bool(torch.cuda.is_available()):
                idx = int(torch.cuda.current_device())
                name = str(torch.cuda.get_device_name(idx))
                props = torch.cuda.get_device_properties(idx)
                memory_mb = int(getattr(props, "total_memory", 0) / (1024 * 1024))
                return True, name or "CUDA GPU", memory_mb, True
        except Exception:
            pass

        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                first_line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
                if first_line:
                    parts = [item.strip() for item in first_line.split(",")]
                    gpu_name = parts[0] if parts else "NVIDIA GPU"
                    gpu_memory_mb = 0
                    if len(parts) > 1:
                        try:
                            gpu_memory_mb = int(float(parts[1]))
                        except Exception:
                            gpu_memory_mb = 0
                    return True, gpu_name, gpu_memory_mb, True
        except Exception:
            pass

        return False, None, 0, False

    @staticmethod
    def _probe_thermal_zone() -> Optional[float]:
        try:
            thermal_file = Path("/sys/class/thermal/thermal_zone0/temp")
            if not thermal_file.exists():
                return None
            raw = thermal_file.read_text(encoding="utf-8", errors="ignore").strip()
            if not raw:
                return None
            return round(float(raw) / 1000.0, 2)
        except Exception:
            return None

    @staticmethod
    def _probe_power_source() -> str:
        try:
            if Path("/sys/class/power_supply/BAT0").exists():
                return "battery"
            if Path("/sys/bus/i2c/drivers/ina3221").exists():
                return "vehicle"
            return "mains"
        except Exception:
            return "unknown"

    @staticmethod
    def _probe_active_links() -> List[str]:
        links: List[str] = []
        try:
            net_root = Path("/sys/class/net")
            if not net_root.exists():
                return links
            for iface in net_root.iterdir():
                if iface.name == "lo":
                    continue
                operstate = iface / "operstate"
                try:
                    state = operstate.read_text(encoding="utf-8", errors="ignore").strip().lower()
                except Exception:
                    continue
                if state == "up":
                    links.append(iface.name)
            return links
        except Exception:
            return []

    @staticmethod
    def _classify(
        cores: int,
        ram_gb: float,
        gpu: bool,
        thermal: Optional[float],
        power: str,
    ) -> HardwareTier:
        del thermal
        if not gpu:
            if cores <= 4 or ram_gb <= 8.0:
                return HardwareTier.CPU_AUSTERE
            return HardwareTier.CPU_STANDARD
        if power in {"battery", "vehicle"}:
            return HardwareTier.VEHICLE_NODE
        if power == "mains" and ram_gb >= 48.0:
            return HardwareTier.FIXED_SITE
        return HardwareTier.EDGE_GPU
