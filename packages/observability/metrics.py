"""In-process metrics collector for provider integration performance."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List


class MetricsCollector:
    """Track counters and latency percentiles per provider."""

    def __init__(self) -> None:
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._latencies: Dict[str, List[float]] = defaultdict(list)

    def increment(self, provider_id: str, metric: str, value: float = 1.0) -> None:
        self._counters[provider_id][metric] += value

    def observe_latency(self, provider_id: str, latency_ms: float) -> None:
        self._latencies[provider_id].append(float(latency_ms))

    def cache_hit(self, provider_id: str) -> None:
        self.increment(provider_id, "cache_hits", 1)

    def cache_miss(self, provider_id: str) -> None:
        self.increment(provider_id, "cache_misses", 1)

    def _percentile(self, values: List[float], percentile: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(math.ceil((percentile / 100.0) * len(sorted_vals))) - 1
        idx = max(0, min(idx, len(sorted_vals) - 1))
        return sorted_vals[idx]

    def provider_metrics(self, provider_id: str) -> Dict[str, float]:
        counters = dict(self._counters.get(provider_id, {}))
        latencies = self._latencies.get(provider_id, [])
        hits = counters.get("cache_hits", 0.0)
        misses = counters.get("cache_misses", 0.0)
        total_cache = hits + misses
        cache_hit_rate = (hits / total_cache) if total_cache else 0.0

        return {
            "fetch_count": counters.get("fetch_count", 0.0),
            "error_count": counters.get("error_count", 0.0),
            "latency_p50": self._percentile(latencies, 50),
            "latency_p95": self._percentile(latencies, 95),
            "latency_p99": self._percentile(latencies, 99),
            "cache_hit_rate": cache_hit_rate,
        }
