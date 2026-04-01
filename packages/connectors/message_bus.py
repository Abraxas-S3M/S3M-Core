"""In-process message bus for air-gap-safe event delivery."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from typing import Any, Callable, Deque, Dict, List


class MessageBus:
    """Simple pub/sub bus with pending event buffering by topic."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)
        self._pending: Dict[str, Deque[Any]] = defaultdict(deque)
        self._lock = Lock()

    def publish(self, topic: str, event: Any) -> None:
        with self._lock:
            self._pending[topic].append(event)
            subscribers = list(self._subscribers.get(topic, []))
        for callback in subscribers:
            callback(event)

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        with self._lock:
            self._subscribers[topic].append(callback)

    def get_pending(self, topic: str) -> List[Any]:
        with self._lock:
            return list(self._pending.get(topic, deque()))
