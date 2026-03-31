"""Jetson runtime telemetry monitor with safe simulation fallback."""

from __future__ import annotations

import glob
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.navigation.models import JetsonStats


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception:
        return None


def _read_float(path: str, scale: float = 1.0) -> Optional[float]:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return float(text) / scale
    except Exception:
        return None


class JetsonMonitor:
    """Collects thermal/power/memory telemetry for tactical edge operations.

    Military context:
    Sustained thermal or power overload can force clock throttling, degrading
    mission reaction time. This monitor supports load shedding decisions before
    autonomy responsiveness collapses.
    """

    def __init__(self) -> None:
        self._simulated = False
        self._last_stats: Optional[JetsonStats] = None
        self._cpu_times_prev: Optional[List[int]] = None
        self._models_memory_mb = 0.0
        self._last_update = datetime.now(timezone.utc)

    def _is_jetson(self) -> bool:
        indicators = [
            "/sys/devices/gpu.0/load",
            "/sys/class/thermal",
            "/etc/nv_tegra_release",
        ]
        return any(os.path.exists(path) for path in indicators)

    def _cpu_utilization(self) -> float:
        text = _read_text("/proc/stat")
        if not text:
            return 0.0
        line = text.splitlines()[0]
        parts = [int(x) for x in line.split()[1:8] if x.isdigit()]
        if len(parts) < 4:
            return 0.0
        total = sum(parts)
        idle = parts[3]
        if self._cpu_times_prev is None:
            self._cpu_times_prev = [total, idle]
            return 0.0
        prev_total, prev_idle = self._cpu_times_prev
        delta_total = max(1, total - prev_total)
        delta_idle = max(0, idle - prev_idle)
        self._cpu_times_prev = [total, idle]
        return max(0.0, min(100.0, 100.0 * (1.0 - delta_idle / delta_total)))

    def _memory_system(self) -> Dict[str, float]:
        meminfo = _read_text("/proc/meminfo") or ""
        values: Dict[str, int] = {}
        for line in meminfo.splitlines():
            if ":" not in line:
                continue
            key, rest = line.split(":", 1)
            token = rest.strip().split()
            if token and token[0].isdigit():
                values[key] = int(token[0])
        total_mb = values.get("MemTotal", 0) / 1024.0
        avail_mb = values.get("MemAvailable", 0) / 1024.0
        used_mb = max(0.0, total_mb - avail_mb)
        return {"used_mb": used_mb, "total_mb": total_mb}

    def _gpu_utilization(self) -> float:
        util = _read_float("/sys/devices/gpu.0/load", scale=10.0)
        if util is not None:
            return max(0.0, min(100.0, util))
        # fallback by parsing tegrastats if available
        try:
            output = subprocess.check_output(["tegrastats", "--interval", "100", "--count", "1"], text=True, timeout=1.5)
            match = re.search(r"GR3D_FREQ\s+(\d+)%", output)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return 0.0

    def _gpu_memory(self) -> Dict[str, float]:
        mem = self._memory_system()
        # Robust fallback: Jetson exposes shared memory; approximate GPU budget.
        total_gpu = max(512.0, mem["total_mb"] * 0.5)
        used_gpu = min(total_gpu, max(0.0, mem["used_mb"] * 0.4))
        return {"used_mb": used_gpu, "total_mb": total_gpu}

    def _temperatures(self) -> Dict[str, float]:
        temps = []
        for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            value = _read_float(path, scale=1000.0)
            if value is not None:
                temps.append(value)
        if not temps:
            return {"gpu_c": 45.0, "cpu_c": 45.0}
        gpu = max(temps)
        cpu = sum(temps) / len(temps)
        return {"gpu_c": gpu, "cpu_c": cpu}

    def _power_draw(self) -> float:
        power_paths = glob.glob("/sys/bus/i2c/drivers/ina3221x/*/iio:device*/in_power*_input")
        values = []
        for path in power_paths:
            val = _read_float(path, scale=1000.0)
            if val is not None:
                values.append(val)
        if values:
            return max(0.0, sum(values))
        return 15.0

    def get_stats(self) -> JetsonStats:
        if not self._is_jetson():
            self._simulated = True
            mem = self._memory_system()
            stats = JetsonStats(
                gpu_utilization_pct=30.0,
                gpu_memory_used_mb=max(256.0, mem["used_mb"] * 0.3),
                gpu_memory_total_mb=max(1024.0, mem["total_mb"] * 0.5),
                cpu_utilization_pct=max(5.0, self._cpu_utilization()),
                ram_used_mb=mem["used_mb"],
                ram_total_mb=mem["total_mb"],
                temperature_gpu_c=45.0,
                temperature_cpu_c=45.0,
                power_draw_watts=15.0,
                power_budget_watts=60.0,
                cuda_version=self.get_cuda_info().get("cuda_version"),
                tensorrt_available=self.get_cuda_info().get("tensorrt_available", False),
                onnx_available=self.get_cuda_info().get("onnxruntime_available", False),
            )
            self._last_stats = stats
            self._last_update = datetime.now(timezone.utc)
            return stats

        self._simulated = False
        mem = self._memory_system()
        gpu_mem = self._gpu_memory()
        temps = self._temperatures()
        cuda_info = self.get_cuda_info()
        stats = JetsonStats(
            gpu_utilization_pct=self._gpu_utilization(),
            gpu_memory_used_mb=gpu_mem["used_mb"],
            gpu_memory_total_mb=gpu_mem["total_mb"],
            cpu_utilization_pct=self._cpu_utilization(),
            ram_used_mb=mem["used_mb"],
            ram_total_mb=mem["total_mb"],
            temperature_gpu_c=temps["gpu_c"],
            temperature_cpu_c=temps["cpu_c"],
            power_draw_watts=self._power_draw(),
            power_budget_watts=60.0,
            cuda_version=cuda_info.get("cuda_version"),
            tensorrt_available=cuda_info.get("tensorrt_available", False),
            onnx_available=cuda_info.get("onnxruntime_available", False),
        )
        self._last_stats = stats
        self._last_update = datetime.now(timezone.utc)
        return stats

    def get_gpu_utilization(self) -> float:
        if self._last_stats is None:
            self.get_stats()
        return self._last_stats.gpu_utilization_pct if self._last_stats else 0.0

    def get_memory_breakdown(self) -> Dict[str, float]:
        stats = self.get_stats()
        return {
            "system_used_mb": stats.ram_used_mb,
            "system_total_mb": stats.ram_total_mb,
            "gpu_used_mb": stats.gpu_memory_used_mb,
            "gpu_total_mb": stats.gpu_memory_total_mb,
            "models_mb": self._models_memory_mb,
        }

    def get_thermal_zones(self) -> List[Dict[str, float]]:
        zones: List[Dict[str, float]] = []
        zone_paths = glob.glob("/sys/class/thermal/thermal_zone*")
        for zone in zone_paths:
            name = _read_text(os.path.join(zone, "type")) or os.path.basename(zone)
            temp = _read_float(os.path.join(zone, "temp"), scale=1000.0)
            trip = _read_float(os.path.join(zone, "trip_point_0_temp"), scale=1000.0)
            if temp is not None:
                zones.append({"zone": name, "temperature_c": temp, "trip_point_c": trip or 95.0})
        if not zones:
            zones = [{"zone": "simulated", "temperature_c": 45.0, "trip_point_c": 95.0}]
        return zones

    def is_thermal_throttling(self) -> bool:
        stats = self.get_stats()
        return stats.is_thermal_throttling()

    def get_cuda_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "cuda_version": None,
            "compute_capability": None,
            "tensorrt_version": None,
            "onnxruntime_version": None,
            "tensorrt_available": False,
            "onnxruntime_available": False,
        }
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                info["cuda_version"] = getattr(torch.version, "cuda", None)
                try:
                    cc = torch.cuda.get_device_capability(0)
                    info["compute_capability"] = f"{cc[0]}.{cc[1]}"
                except Exception:
                    pass
        except Exception:
            pass
        try:
            import tensorrt  # type: ignore

            info["tensorrt_available"] = True
            info["tensorrt_version"] = getattr(tensorrt, "__version__", None)
        except Exception:
            pass
        try:
            import onnxruntime as ort  # type: ignore

            info["onnxruntime_available"] = True
            info["onnxruntime_version"] = getattr(ort, "__version__", None)
        except Exception:
            pass
        return info

    def recommend_model_budget(self) -> float:
        stats = self.get_stats()
        headroom = 0.2
        available = max(0.0, (stats.ram_total_mb - stats.ram_used_mb) - (stats.ram_total_mb * headroom))
        if available <= 0.0:
            return 256.0
        return available

    def is_simulated(self) -> bool:
        if self._last_stats is None:
            self.get_stats()
        return self._simulated
