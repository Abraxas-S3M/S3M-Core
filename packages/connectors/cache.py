"""In-memory LRU cache with TTL for integration accelerators."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class Cache:
    """TTL-aware LRU cache for provider response and lookup reuse."""

    def __init__(self, max_size: int = 1024) -> None:
        self.max_size = int(max_size)
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._store.items() if v.expires_at <= now]
        for key in expired:
            self._store.pop(key, None)

    def get(self, key: str) -> Optional[Any]:
        self._evict_expired()
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        self._store.move_to_end(key)
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._evict_expired()
        expires_at = time.time() + max(int(ttl_seconds), 1)
        self._store[key] = _CacheEntry(value=value, expires_at=expires_at)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def stats(self) -> Dict[str, float]:
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total else 0.0
        return {
            "size": len(self._store),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }
