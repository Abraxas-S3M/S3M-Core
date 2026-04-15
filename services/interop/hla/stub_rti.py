"""Deterministic offline RTI stub for air-gapped HLA federation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _StubObjectState:
    class_name: str
    object_handle: int
    attributes: Dict[str, Any]
    logical_time: float


class HLAStubRTI:
    """Offline IEEE-1516 RTI replacement used for tactical air-gapped execution."""

    def __init__(self, time_step: float = 0.1):
        self.time_step = float(time_step) if float(time_step) > 0 else 0.1
        self.federation_name: str = ""
        self.fom_path: str = ""
        self.joined = False
        self.current_time = 0.0
        self._published_classes: Dict[str, set[str]] = {}
        self._subscribed_classes: Dict[str, set[str]] = {}
        self._objects: Dict[int, _StubObjectState] = {}
        self._next_handle = 1
        self._interaction_log: List[Dict[str, Any]] = []
        self._object_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._interaction_callbacks: List[Callable[[Dict[str, Any]], None]] = []

    def create_federation(self, name: str, fom_path: str) -> bool:
        if not str(name).strip() or not str(fom_path).strip():
            return False
        self.federation_name = str(name).strip()
        self.fom_path = str(fom_path).strip()
        self.current_time = 0.0
        self._objects.clear()
        self._interaction_log.clear()
        return True

    def join_federation(self, name: str) -> bool:
        if not self.federation_name or self.federation_name != str(name).strip():
            return False
        self.joined = True
        return True

    def publish_object_class(self, class_name: str, attributes: List[str]) -> bool:
        if not self.joined or not str(class_name).strip():
            return False
        self._published_classes[str(class_name)] = {str(attr) for attr in attributes}
        return True

    def subscribe_object_class(self, class_name: str, attributes: List[str]) -> bool:
        if not self.joined or not str(class_name).strip():
            return False
        self._subscribed_classes[str(class_name)] = {str(attr) for attr in attributes}
        return True

    def update_object(self, class_name: str, object_handle: int, attributes: Dict[str, Any]) -> bool:
        if not self.joined or not str(class_name).strip() or not isinstance(attributes, dict):
            return False

        handle = int(object_handle)
        if handle <= 0:
            handle = self._next_handle
            self._next_handle += 1

        state = _StubObjectState(
            class_name=str(class_name),
            object_handle=handle,
            attributes=dict(attributes),
            logical_time=self.current_time,
        )
        self._objects[handle] = state
        self._reflect_to_subscribers(state)
        return True

    def send_interaction(self, class_name: str, parameters: Dict[str, Any]) -> bool:
        if not self.joined or not str(class_name).strip() or not isinstance(parameters, dict):
            return False
        interaction = {
            "class_name": str(class_name),
            "parameters": dict(parameters),
            "logical_time": self.current_time,
        }
        self._interaction_log.append(interaction)
        for callback in list(self._interaction_callbacks):
            callback(dict(interaction))
        return True

    def register_object_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._object_callbacks.append(callback)

    def register_interaction_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._interaction_callbacks.append(callback)

    def resign_federation(self) -> bool:
        self.joined = False
        return True

    def destroy_federation(self, name: str) -> bool:
        if self.federation_name != str(name).strip():
            return False
        self.joined = False
        self.federation_name = ""
        self.fom_path = ""
        self.current_time = 0.0
        self._objects.clear()
        self._interaction_log.clear()
        self._published_classes.clear()
        self._subscribed_classes.clear()
        return True

    def advance_time(self, step: float) -> bool:
        delta = float(step)
        if delta <= 0:
            return False
        self.current_time = round(self.current_time + delta, 6)
        return True

    def get_objects(self) -> List[Dict[str, Any]]:
        return [
            {
                "class_name": state.class_name,
                "object_handle": handle,
                "attributes": dict(state.attributes),
                "logical_time": state.logical_time,
            }
            for handle, state in sorted(self._objects.items(), key=lambda row: row[0])
        ]

    def get_interactions(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._interaction_log]

    def status(self) -> Dict[str, Any]:
        return {
            "mode": "stub",
            "federation_name": self.federation_name,
            "joined": self.joined,
            "object_count": len(self._objects),
            "interaction_count": len(self._interaction_log),
            "logical_time": self.current_time,
            "time_step": self.time_step,
        }

    def health_check(self) -> Dict[str, Any]:
        status = self.status()
        status["status"] = "operational"
        return status

    def _reflect_to_subscribers(self, state: _StubObjectState) -> None:
        if state.class_name not in self._subscribed_classes:
            return
        reflection = {
            "class_name": state.class_name,
            "object_handle": state.object_handle,
            "attributes": dict(state.attributes),
            "logical_time": state.logical_time,
        }
        # Tactical federation stub behavior: deterministic immediate loopback keeps
        # exercise playback reproducible when no external RTI middleware is present.
        for callback in list(self._object_callbacks):
            callback(dict(reflection))
