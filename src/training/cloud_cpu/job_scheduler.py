"""Duty-cycle scheduler for cloud CPU adaptation.

Military/tactical context:
The scheduler enforces burst training windows followed by cool-down sleep
windows so the trainer can keep operating on constrained shared CPUs without
starving colocated mission services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DutyCycle:
    """Normalized duty cycle settings."""

    train_seconds: float = 60.0
    sleep_seconds: float = 10.0


class JobScheduler:
    """Simple train/sleep cadence with optional reduced duty mode."""

    def __init__(self, train_seconds: float = 60.0, sleep_seconds: float = 10.0) -> None:
        self._default = DutyCycle(
            train_seconds=max(1.0, float(train_seconds)),
            sleep_seconds=max(0.5, float(sleep_seconds)),
        )
        self._active = self._default
        self._phase = "train"
        self._phase_started_at = time.monotonic()
        self._reduced = False

    def should_train(self) -> bool:
        """Return True while the scheduler is in training phase."""
        self._advance_phase_if_needed()
        return self._phase == "train"

    def should_sleep(self) -> bool:
        """Return True while the scheduler is in sleep phase."""
        self._advance_phase_if_needed()
        return self._phase == "sleep"

    def sleep_duration(self) -> float:
        """Return configured sleep duration for the active duty cycle."""
        self._phase = "sleep"
        self._phase_started_at = time.monotonic()
        return self._active.sleep_seconds

    def apply_throttle_recommendation(self, recommended_action: Any) -> None:
        """Adjust duty cycle using ResourceGuard recommendation values."""
        action = str(getattr(recommended_action, "value", recommended_action)).strip().lower()
        if action in {"pause", "hard_pause"}:
            # Tactical backoff: extend sleep aggressively during resource stress.
            self._active = DutyCycle(train_seconds=15.0, sleep_seconds=max(20.0, self._default.sleep_seconds * 4.0))
            self._reduced = True
            self._phase = "sleep"
            self._phase_started_at = time.monotonic()
            return
        if action in {"eval_only", "reduced", "throttle"}:
            self.enter_reduced_duty()
            return
        self.exit_reduced_duty()

    def enter_reduced_duty(self) -> None:
        """Reduce train window and increase sleep window."""
        self._active = DutyCycle(
            train_seconds=max(15.0, self._default.train_seconds * 0.5),
            sleep_seconds=max(self._default.sleep_seconds * 2.0, self._default.sleep_seconds),
        )
        self._reduced = True

    def exit_reduced_duty(self) -> None:
        """Restore default duty cycle."""
        self._active = self._default
        self._reduced = False

    def reset_cycle(self) -> None:
        """Restart duty cycle at training phase."""
        self._phase = "train"
        self._phase_started_at = time.monotonic()

    def _advance_phase_if_needed(self) -> None:
        elapsed = time.monotonic() - self._phase_started_at
        if self._phase == "train" and elapsed >= self._active.train_seconds:
            self._phase = "sleep"
            self._phase_started_at = time.monotonic()
            return
        if self._phase == "sleep" and elapsed >= self._active.sleep_seconds:
            self._phase = "train"
            self._phase_started_at = time.monotonic()
