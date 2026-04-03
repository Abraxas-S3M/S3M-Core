"""Boot-time hardware profiling for austere S3M deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import glob
import logging
import os
import socket
import subprocess
from typing import Dict, List, Optional

logger = logging.getLogger("s3m.edge_runtime.hardware_profiler")


class HardwareTier(str, Enum):
    CPU_AUSTERE = "CPU_AUSTERE"
    CPU_STANDARD = "CPU_STANDARD"
    EDGE_GPU = "EDGE_GPU"
    VEHICLE_NODE = "VEHICLE_NODE"
    FIXED_SITE = "FIXED_SITE"


@dataclass(slots=True)
class NodeProfile:
    tier: HardwareTier
    total_memory_mb: int
    cpu_cores: int
    gpu_available: bool
    gpu_name: str = "none"
    gpu_memory_mb: int = 0
    avg_thermal_celsius: float = 0.0
    network_interfaces: Dict[str, str] = field(default_factory=dict)
    profiled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class HardwareProfiler:
    """Profiles compute, thermal, and link surfaces at node boot."""

    def run(self) -> NodeProfile:
        memory_mb = self._read_total_memory_mb()
        cpu_cores = os.cpu_count() or 1
        gpu_name, gpu_memory_mb = self._read_gpu_info()
        gpu_available = gpu_name != "none"
        avg_temp = self._read_average_thermal_celsius()
        interfaces = self._read_network_interfaces()
        tier = self._classify_tier(
            memory_mb=memory_mb,
            gpu_available=gpu_available,
            interfaces=interfaces,
        )
        profile = NodeProfile(
            tier=tier,
            total_memory_mb=memory_mb,
            cpu_cores=cpu_cores,
            gpu_available=gpu_available,
            gpu_name=gpu_name,
            gpu_memory_mb=gpu_memory_mb,
            avg_thermal_celsius=avg_temp,
            network_interfaces=interfaces,
        )
        logger.info(
            "Hardware profile complete tier=%s mem_mb=%s cpu=%s gpu=%s ifaces=%s",
            profile.tier.value,
            profile.total_memory_mb,
            profile.cpu_cores,
            profile.gpu_name,
            len(profile.network_interfaces),
        )
        return profile

    def _read_total_memory_mb(self) -> int:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return max(1, kb // 1024)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Failed reading /proc/meminfo: %s", exc)
        return 1024

    def _read_gpu_info(self) -> tuple[str, int]:
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ]
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            first = out.strip().splitlines()[0]
            name, mem = [part.strip() for part in first.split(",", maxsplit=1)]
            return name or "nvidia", int(float(mem))
        except Exception:
            # Tactical fallback: Jetson-class nodes may expose GPU devices without nvidia-smi.
            if os.path.exists("/dev/nvhost-gpu") or os.path.exists("/dev/nvidia0"):
                return "embedded_nvidia", 0
        return "none", 0

    def _read_average_thermal_celsius(self) -> float:
        temps: List[float] = []
        for zone in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                with open(zone, "r", encoding="utf-8") as handle:
                    raw = handle.read().strip()
                value = float(raw)
                if value > 1000:
                    value = value / 1000.0
                if value > 0:
                    temps.append(value)
            except Exception:
                continue
        if not temps:
            return 0.0
        return round(sum(temps) / len(temps), 2)

    def _read_network_interfaces(self) -> Dict[str, str]:
        states: Dict[str, str] = {}
        try:
            for _, name in socket.if_nameindex():
                if name == "lo":
                    continue
                operstate_path = f"/sys/class/net/{name}/operstate"
                try:
                    with open(operstate_path, "r", encoding="utf-8") as handle:
                        state = handle.read().strip()
                except Exception:
                    state = "unknown"
                states[name] = state
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Unable to enumerate network interfaces: %s", exc)
        return states

    def _classify_tier(
        self,
        memory_mb: int,
        gpu_available: bool,
        interfaces: Dict[str, str],
    ) -> HardwareTier:
        names = {name.lower() for name in interfaces}
        has_wired = any(n.startswith(("eth", "en")) for n in names)
        has_mobile = any(
            token in n for n in names for token in ("wwan", "lte", "cell", "mesh", "wlan")
        )

        if gpu_available and has_wired and memory_mb >= 32768:
            return HardwareTier.FIXED_SITE
        if gpu_available and has_mobile:
            return HardwareTier.VEHICLE_NODE
        if gpu_available:
            return HardwareTier.EDGE_GPU
        if memory_mb >= 16384:
            return HardwareTier.CPU_STANDARD
        return HardwareTier.CPU_AUSTERE
