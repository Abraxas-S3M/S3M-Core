"""Token bucket rate limiter for per-provider request budgets."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Thread-safe token bucket limiter measured in requests-per-minute."""

    def __init__(self, rpm: int) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be > 0")
        self.rpm = int(rpm)
        self.capacity = float(rpm)
        self._tokens = float(rpm)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = max(now - self._last_refill, 0.0)
        tokens_per_second = self.rpm / 60.0
        self._tokens = min(self.capacity, self._tokens + elapsed * tokens_per_second)
        self._last_refill = now

    def acquire(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def wait(self) -> None:
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                tokens_per_second = self.rpm / 60.0
                needed = max(1.0 - self._tokens, 0.0)
                sleep_for = needed / tokens_per_second if tokens_per_second > 0 else 0.1
            time.sleep(max(min(sleep_for, 1.0), 0.01))

    def reset(self) -> None:
        with self._lock:
            self._tokens = self.capacity
            self._last_refill = time.monotonic()
