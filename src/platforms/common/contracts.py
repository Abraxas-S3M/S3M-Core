"""Protocol contracts for platform and payload integration adapters.

These runtime-checkable protocols enforce a minimal interoperability baseline
between tactical vehicles, payloads, and shared control services.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .messages import PayloadState, PlatformState


@runtime_checkable
class PlatformAdapter(Protocol):
    """Minimal platform interface required by S3M integration flows."""

    def connect(self) -> bool:
        """Establish local control link for tactical command and telemetry."""

    def read_state(self) -> PlatformState:
        """Return the latest platform state used by autonomy and safety."""


@runtime_checkable
class PayloadAdapter(Protocol):
    """Minimal payload interface required by engagement and safety flows."""

    def connect(self) -> bool:
        """Establish payload control path before arming or queuing targets."""

    def read_state(self) -> PayloadState:
        """Return payload status used for fire-control decisions."""
