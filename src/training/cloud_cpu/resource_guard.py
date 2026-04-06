"""Resource backpressure advisor for cloud CPU training.

Military/tactical context:
When training and operator-facing API traffic share the same host, uncontrolled
CPU pressure can degrade command response latency. This guard reports resource
health and recommends throttle actions without directly enforcing them.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib import request
from urllib.error import URLError

logger = logging.getLogger("s3m.training.cloud_cpu.resource_guard")

try:
    import psutil

    PSUTIL_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore[assignment]
    PSUTIL_AVAILABLE = False


class ThrottleAction(str, Enum):
    """Advisory actions for callers that orchestrate trainer workloads."""

    NORMAL = "normal"
    REDUCE_BATCH = "reduce_batch"
    EVAL_ONLY = "eval_only"
    PAUSE = "pause"


@dataclass
class ResourceStatus:
    """Snapshot of host utilization and recommended action."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    api_latency_ms: Optional[float] = None
    cpu_ok: bool = True
    memory_ok: bool = True
    api_latency_ok: bool = True
    recommended_action: ThrottleAction = ThrottleAction.NORMAL


class ResourceGuard:
    """Monitors CPU/memory/API responsiveness and advises throttle level."""

    def __init__(
        self,
        api_cpu_threads: int = 2,
        trainer_cpu_threads: int = 6,
        api_latency_target_ms: float = 500.0,
        cpu_threshold_pct: float = 85.0,
        memory_threshold_pct: float = 88.0,
        api_health_url: Optional[str] = None,
        api_health_timeout_s: float = 1.5,
    ) -> None:
        self._api_threads = max(1, int(api_cpu_threads))
        self._trainer_threads = max(1, int(trainer_cpu_threads))
        self._latency_target_ms = float(api_latency_target_ms)
        self._cpu_threshold_pct = float(cpu_threshold_pct)
        self._memory_threshold_pct = float(memory_threshold_pct)
        self._api_health_url = api_health_url
        self._api_health_timeout_s = float(api_health_timeout_s)

        # Constrain BLAS/OpenMP thread pools so API threads retain headroom.
        os.environ.setdefault("OMP_NUM_THREADS", str(self._trainer_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(self._trainer_threads))
        os.environ.setdefault("OPENBLAS_NUM_THREADS", str(self._trainer_threads))

    def check(self) -> ResourceStatus:
        """Return current resource status and a throttle recommendation."""
        status = ResourceStatus()
        status.cpu_percent = self._cpu_percent()
        status.memory_percent = self._memory_percent()
        status.api_latency_ms = self._api_latency_ms()

        status.cpu_ok = status.cpu_percent <= self._cpu_threshold_pct
        status.memory_ok = status.memory_percent <= self._memory_threshold_pct
        status.api_latency_ok = (
            status.api_latency_ms is None or status.api_latency_ms <= self._latency_target_ms
        )

        if not status.memory_ok or status.cpu_percent >= 97.0:
            status.recommended_action = ThrottleAction.PAUSE
        elif not status.api_latency_ok:
            status.recommended_action = ThrottleAction.EVAL_ONLY
        elif not status.cpu_ok:
            status.recommended_action = ThrottleAction.REDUCE_BATCH
        else:
            status.recommended_action = ThrottleAction.NORMAL
        return status

    def _cpu_percent(self) -> float:
        if PSUTIL_AVAILABLE and psutil is not None:
            return float(psutil.cpu_percent(interval=0.2))
        return self._cpu_percent_from_proc()

    def _memory_percent(self) -> float:
        if PSUTIL_AVAILABLE and psutil is not None:
            return float(psutil.virtual_memory().percent)
        return self._memory_percent_from_proc()

    def _api_latency_ms(self) -> Optional[float]:
        if not self._api_health_url:
            return None
        started = time.perf_counter()
        try:
            with request.urlopen(
                self._api_health_url,
                timeout=self._api_health_timeout_s,
            ) as response:
                # Health endpoint should return 2xx for ready state.
                if response.status >= 500:
                    return self._latency_target_ms + 1.0
            return (time.perf_counter() - started) * 1000.0
        except URLError:
            logger.warning("API health probe failed: %s", self._api_health_url)
            return self._latency_target_ms + 1.0
        except Exception:
            logger.exception("Unexpected API health probe error")
            return self._latency_target_ms + 1.0

    @staticmethod
    def _cpu_percent_from_proc() -> float:
        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as handle:
                load_1 = float(handle.read().split()[0])
            cpu_count = max(1, int(os.cpu_count() or 1))
            return min(100.0, (load_1 / cpu_count) * 100.0)
        except (OSError, ValueError):
            return 0.0

    @staticmethod
    def _memory_percent_from_proc() -> float:
        mem_total = 0
        mem_available = 0
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_available = int(line.split()[1])
            if mem_total <= 0:
                return 0.0
            return ((mem_total - mem_available) / mem_total) * 100.0
        except (OSError, ValueError):
            return 0.0
