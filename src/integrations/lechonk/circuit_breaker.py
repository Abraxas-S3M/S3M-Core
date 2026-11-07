"""Lightweight circuit breaker for Le Chonk planning backend (no external deps)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Stop hammering an unavailable private inference endpoint."""

    failure_threshold: int = 3
    recovery_timeout_s: float = 60.0
    half_open_successes_required: int = 1
    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_successes: int = field(default=0, init=False)

    @property
    def state(self) -> BreakerState:
        if self._state == BreakerState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout_s:
                self._state = BreakerState.HALF_OPEN
                self._half_open_successes = 0
        return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == BreakerState.CLOSED:
            return True
        if state == BreakerState.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        if self.state == BreakerState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_successes_required:
                self._state = BreakerState.CLOSED
                self._failure_count = 0
        else:
            self._failure_count = 0
            self._state = BreakerState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        if self.state == BreakerState.HALF_OPEN:
            self._trip()
            return
        if self._failure_count >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_successes = 0
