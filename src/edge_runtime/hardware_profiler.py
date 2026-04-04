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
import re
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
    # CPU ISA capability flags — detected at boot.
    avx2_supported: bool = False
    avx512_supported: bool = False
    avx512_bf16_supported: bool = False
    avx512_vnni_supported: bool = False
    arm_neon_supported: bool = False
    arm_sve_supported: bool = False
    numa_node_count: int = 1
    simd_register_width_bits: int = 128  # 128/256/512
    # Tactical metadata enables commanders to select safe on-node training paths.
    tier_metadata: Dict[str, object] = field(default_factory=dict)
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
            "avx2_supported": self.avx2_supported,
            "avx512_supported": self.avx512_supported,
            "avx512_bf16_supported": self.avx512_bf16_supported,
            "avx512_vnni_supported": self.avx512_vnni_supported,
            "arm_neon_supported": self.arm_neon_supported,
            "arm_sve_supported": self.arm_sve_supported,
            "numa_node_count": self.numa_node_count,
            "simd_register_width_bits": self.simd_register_width_bits,
            "tier_metadata": dict(self.tier_metadata),
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
        isa_capabilities = self._probe_isa_capabilities()
        numa_node_count = self._probe_numa_nodes()
        tier = self._classify(
            cores=cpu_cores,
            ram_gb=ram_total_gb,
            gpu=gpu_detected,
            thermal=thermal_zone_c,
            power=power_source,
            isa_capabilities=isa_capabilities,
        )
        tier_metadata = self._tier_metadata(tier=tier, isa_capabilities=isa_capabilities, numa_node_count=numa_node_count)
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
            avx2_supported=bool(isa_capabilities.get("avx2_supported", False)),
            avx512_supported=bool(isa_capabilities.get("avx512_supported", False)),
            avx512_bf16_supported=bool(isa_capabilities.get("avx512_bf16_supported", False)),
            avx512_vnni_supported=bool(isa_capabilities.get("avx512_vnni_supported", False)),
            arm_neon_supported=bool(isa_capabilities.get("arm_neon_supported", False)),
            arm_sve_supported=bool(isa_capabilities.get("arm_sve_supported", False)),
            numa_node_count=max(1, int(numa_node_count)),
            simd_register_width_bits=max(128, int(isa_capabilities.get("simd_register_width_bits", 128))),
            tier_metadata=tier_metadata,
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
    def _extract_feature_tokens(raw: str) -> set[str]:
        """Extract lowercase CPU feature tokens from cpuinfo/lscpu-like text."""
        tokens: set[str] = set()
        pattern = re.compile(r"^(flags|features)\s*:\s*(.+)$", flags=re.IGNORECASE | re.MULTILINE)
        for match in pattern.finditer(raw):
            for token in match.group(2).strip().lower().split():
                if token:
                    tokens.add(token)
        return tokens

    @staticmethod
    def _probe_isa_capabilities() -> dict:
        """Detect CPU ISA extensions with conservative, non-crashing fallbacks."""
        capabilities = {
            "avx2_supported": False,
            "avx512_supported": False,
            "avx512_bf16_supported": False,
            "avx512_vnni_supported": False,
            "arm_neon_supported": False,
            "arm_sve_supported": False,
            "simd_register_width_bits": 128,
        }
        arch = str(platform.machine()).lower()
        feature_tokens: set[str] = set()

        try:
            cpuinfo = Path("/proc/cpuinfo")
            if cpuinfo.exists():
                feature_tokens = HardwareProfiler._extract_feature_tokens(
                    cpuinfo.read_text(encoding="utf-8", errors="ignore")
                )
        except Exception:
            feature_tokens = set()

        if not feature_tokens and arch in {"arm64", "aarch64"} and platform.system().lower() == "darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-a"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0:
                    sysctl_text = result.stdout.lower()
                    if "hw.optional.neon: 1" in sysctl_text or "hw.optional.advsimd: 1" in sysctl_text:
                        feature_tokens.update({"neon", "asimd"})
                    if "hw.optional.sve: 1" in sysctl_text or "hw.optional.arm.feat_sve: 1" in sysctl_text:
                        feature_tokens.add("sve")
            except Exception:
                feature_tokens = set()

        if not feature_tokens:
            try:
                result = subprocess.run(
                    ["lscpu"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0:
                    feature_tokens = HardwareProfiler._extract_feature_tokens(result.stdout)
            except Exception:
                feature_tokens = set()

        if arch in {"x86_64", "amd64", "i386", "i686"}:
            avx512_vnni_aliases = {"avx512_vnni", "avx_vnni", "avxvnni"}
            capabilities["avx2_supported"] = "avx2" in feature_tokens
            capabilities["avx512_supported"] = "avx512f" in feature_tokens or "avx512" in feature_tokens
            capabilities["avx512_bf16_supported"] = (
                "avx512_bf16" in feature_tokens or "avx512bf16" in feature_tokens
            )
            capabilities["avx512_vnni_supported"] = any(flag in feature_tokens for flag in avx512_vnni_aliases)
            if capabilities["avx512_supported"]:
                capabilities["simd_register_width_bits"] = 512
            elif capabilities["avx2_supported"]:
                capabilities["simd_register_width_bits"] = 256
            return capabilities

        if arch in {"arm64", "aarch64"}:
            capabilities["arm_neon_supported"] = any(token in feature_tokens for token in {"neon", "asimd", "advsimd"})
            capabilities["arm_sve_supported"] = any(token == "sve" or token.startswith("sve") for token in feature_tokens)
            if capabilities["arm_sve_supported"]:
                try:
                    raw = Path("/proc/sys/abi/sve_default_vector_length").read_text(
                        encoding="utf-8",
                        errors="ignore",
                    ).strip()
                    sve_bytes = int(raw)
                    capabilities["simd_register_width_bits"] = max(128, sve_bytes * 8)
                except Exception:
                    capabilities["simd_register_width_bits"] = 256
            elif capabilities["arm_neon_supported"]:
                capabilities["simd_register_width_bits"] = 128
            return capabilities

        return capabilities

    @staticmethod
    def _probe_numa_nodes() -> int:
        """Count NUMA nodes from sysfs with safe fallback."""
        try:
            nodes_root = Path("/sys/devices/system/node")
            if nodes_root.exists():
                count = sum(
                    1
                    for entry in nodes_root.iterdir()
                    if entry.is_dir() and re.fullmatch(r"node[0-9]+", entry.name)
                )
                if count > 0:
                    return count
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["lscpu"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0:
                match = re.search(r"^NUMA node\(s\):\s*([0-9]+)\s*$", result.stdout, flags=re.MULTILINE)
                if match:
                    return max(1, int(match.group(1)))
        except Exception:
            pass
        return 1

    @staticmethod
    def _tier_metadata(tier: HardwareTier, isa_capabilities: Dict[str, object], numa_node_count: int) -> Dict[str, object]:
        metadata: Dict[str, object] = {"numa_node_count": max(1, int(numa_node_count))}
        if tier is HardwareTier.CPU_STANDARD and bool(isa_capabilities.get("avx512_bf16_supported", False)):
            metadata["cpu_precision_path"] = "avx512_bf16"
            metadata["tier_note"] = "cpu_standard_bf16_accelerated"
        return metadata

    @staticmethod
    def _classify(
        cores: int,
        ram_gb: float,
        gpu: bool,
        thermal: Optional[float],
        power: str,
        isa_capabilities: Optional[Dict[str, object]] = None,
    ) -> HardwareTier:
        del thermal
        isa = isa_capabilities or {}
        bf16_capable = bool(isa.get("avx512_bf16_supported", False))
        if not gpu:
            if cores <= 4 or ram_gb <= 8.0:
                if bf16_capable and ram_gb >= 8.0:
                    return HardwareTier.CPU_STANDARD
                return HardwareTier.CPU_AUSTERE
            return HardwareTier.CPU_STANDARD
        if power in {"battery", "vehicle"}:
            return HardwareTier.VEHICLE_NODE
        if power == "mains" and ram_gb >= 48.0:
            return HardwareTier.FIXED_SITE
        return HardwareTier.EDGE_GPU
