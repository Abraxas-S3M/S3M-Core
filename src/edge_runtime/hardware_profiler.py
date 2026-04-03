"""
Boot-time hardware capability profiler.
Classifies the node into a runtime tier so every downstream service
knows its resource ceiling before loading anything.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class HardwareTier(Enum):
    """Runtime tier determines which services and models are permitted."""

    CPU_AUSTERE = "cpu_austere"  # <=4 cores, <=8 GB RAM, no GPU
    CPU_STANDARD = "cpu_standard"  # >4 cores, >8 GB RAM, no GPU
    EDGE_GPU = "edge_gpu"  # Jetson-class GPU present
    VEHICLE_NODE = "vehicle_node"  # GPU + constrained thermal/power
    FIXED_SITE = "fixed_site"  # Full server, may still be bandwidth-limited


@dataclass
class NodeProfile:
    """Immutable snapshot of node capabilities taken at boot."""

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
    power_source: str  # "mains" | "battery" | "vehicle" | "unknown"
    active_links: List[str] = field(default_factory=list)
    profiled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "cpu_cores": self.cpu_cores,
            "cpu_arch": self.cpu_arch,
            "ram_total_gb": round(self.ram_total_gb, 2),
            "ram_available_gb": round(self.ram_available_gb, 2),
            "disk_total_gb": round(self.disk_total_gb, 2),
            "disk_free_gb": round(self.disk_free_gb, 2),
            "gpu_detected": self.gpu_detected,
            "gpu_name": self.gpu_name,
            "gpu_memory_mb": self.gpu_memory_mb,
            "cuda_available": self.cuda_available,
            "thermal_zone_c": self.thermal_zone_c,
            "power_source": self.power_source,
            "active_links": self.active_links,
            "profiled_at": self.profiled_at,
        }


class HardwareProfiler:
    """Runs once at boot. All results cached in self.profile."""

    def __init__(self) -> None:
        self.profile: Optional[NodeProfile] = None

    # -- Public API ---------------------------------------------------------

    def run(self) -> NodeProfile:
        """Profile the current node and return an immutable NodeProfile."""
        cpu_cores = os.cpu_count() or 1
        cpu_arch = platform.machine()
        ram_total, ram_avail = self._probe_memory()
        disk_total, disk_free = self._probe_disk()
        gpu_detected, gpu_name, gpu_mem, cuda_ok = self._probe_gpu()
        thermal = self._probe_thermal()
        power = self._probe_power()
        links = self._probe_links()
        tier = self._classify(cpu_cores, ram_total, gpu_detected, thermal, power)

        self.profile = NodeProfile(
            tier=tier,
            cpu_cores=cpu_cores,
            cpu_arch=cpu_arch,
            ram_total_gb=ram_total,
            ram_available_gb=ram_avail,
            disk_total_gb=disk_total,
            disk_free_gb=disk_free,
            gpu_detected=gpu_detected,
            gpu_name=gpu_name,
            gpu_memory_mb=gpu_mem,
            cuda_available=cuda_ok,
            thermal_zone_c=thermal,
            power_source=power,
            active_links=links,
        )
        return self.profile

    # -- Probes -------------------------------------------------------------

    @staticmethod
    def _probe_memory() -> tuple[float, float]:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                lines = f.readlines()
            info = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    info[parts[0].strip()] = int(parts[1].strip().split()[0])
            total = info.get("MemTotal", 0) / (1024 * 1024)
            avail = info.get("MemAvailable", info.get("MemFree", 0)) / (1024 * 1024)
            return total, avail
        except Exception:
            return 4.0, 2.0  # conservative fallback for denied environments

    @staticmethod
    def _probe_disk() -> tuple[float, float]:
        try:
            usage = shutil.disk_usage("/")
            return usage.total / (1024**3), usage.free / (1024**3)
        except Exception:
            return 32.0, 16.0

    @staticmethod
    def _probe_gpu() -> tuple[bool, Optional[str], int, bool]:
        # Prefer CUDA runtime detection to identify Jetson/offline deployments.
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                mem = int(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024))
                return True, name, mem, True
        except Exception:
            pass

        # Fallback for systems where CUDA Python bindings are unavailable.
        try:
            import subprocess

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                name = parts[0].strip()
                mem = int(float(parts[1].strip())) if len(parts) > 1 else 0
                return True, name, mem, True
        except Exception:
            pass
        return False, None, 0, False

    @staticmethod
    def _probe_thermal() -> Optional[float]:
        try:
            zones = sorted([f for f in os.listdir("/sys/class/thermal/") if f.startswith("thermal_zone")])
            if zones:
                with open(f"/sys/class/thermal/{zones[0]}/temp", "r", encoding="utf-8") as f:
                    return int(f.read().strip()) / 1000.0
        except Exception:
            pass
        return None

    @staticmethod
    def _probe_power() -> str:
        # Tactical context: classify power budget to avoid selecting models that
        # could destabilize vehicle-mounted compute nodes in contested operations.
        try:
            if os.path.exists("/sys/class/power_supply/BAT0"):
                return "battery"
            if os.path.exists("/sys/bus/i2c/drivers/ina3221"):
                return "vehicle"  # Jetson power rail -> likely embedded
        except Exception:
            pass
        return "mains"

    @staticmethod
    def _probe_links() -> List[str]:
        """Detect which network-class interfaces are UP."""
        links: List[str] = []
        try:
            for iface in os.listdir("/sys/class/net/"):
                if iface == "lo":
                    continue
                state_path = f"/sys/class/net/{iface}/operstate"
                if os.path.exists(state_path):
                    with open(state_path, "r", encoding="utf-8") as f:
                        if f.read().strip() == "up":
                            links.append(iface)
        except Exception:
            pass
        return links

    # -- Classifier ---------------------------------------------------------

    @staticmethod
    def _classify(
        cores: int,
        ram_gb: float,
        gpu: bool,
        thermal: Optional[float],
        power: str,
    ) -> HardwareTier:
        _ = thermal  # reserved for future thermal de-rate logic
        if gpu and power == "vehicle":
            return HardwareTier.VEHICLE_NODE
        if gpu and ram_gb >= 16:
            return HardwareTier.FIXED_SITE if ram_gb >= 48 else HardwareTier.EDGE_GPU
        if cores <= 4 or ram_gb <= 8:
            return HardwareTier.CPU_AUSTERE
        return HardwareTier.CPU_STANDARD
