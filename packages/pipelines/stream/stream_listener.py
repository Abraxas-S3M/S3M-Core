"""Abstract streaming listener base for websocket and SSE providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class StreamListenerBase(ABC):
    """Base interface for provider stream connectors."""

    def __init__(self, on_event: Callable[[Any], None]) -> None:
        self.on_event = on_event

    @abstractmethod
    def connect(self) -> None:
        """Open stream connection."""

    @abstractmethod
    def listen(self) -> None:
        """Consume stream events and route to callback."""

    @abstractmethod
    def stop(self) -> None:
        """Terminate stream listener."""
