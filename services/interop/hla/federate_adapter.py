"""Federate adapter for IEEE-1516 HLA federation participation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Protocol
from xml.etree import ElementTree

from services.interop.dis.coordinate_converter import DISCoordinateConverter
from services.interop.models import DISWorldCoordinate
from services.interop.hla.stub_rti import HLAStubRTI


class RTIBackend(Protocol):
    """Interface that concrete RTI backends (stub/CERTI/Pitch/MAK) must implement."""

    def create_federation(self, name: str, fom_path: str) -> bool: ...

    def join_federation(self, name: str) -> bool: ...

    def publish_object_class(self, class_name: str, attributes: List[str]) -> bool: ...

    def subscribe_object_class(self, class_name: str, attributes: List[str]) -> bool: ...

    def update_object(self, class_name: str, object_handle: int, attributes: Dict[str, Any]) -> bool: ...

    def register_object_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None: ...

    def send_interaction(self, class_name: str, parameters: Dict[str, Any]) -> bool: ...

    def register_interaction_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None: ...

    def resign_federation(self) -> bool: ...

    def destroy_federation(self, name: str) -> bool: ...

    def advance_time(self, step: float) -> bool: ...

    def status(self) -> Dict[str, Any]: ...

    def health_check(self) -> Dict[str, Any]: ...

    def get_objects(self) -> List[Dict[str, Any]]: ...

    def get_interactions(self) -> List[Dict[str, Any]]: ...


class HLAFederateAdapter:
    """S3M HLA federate adapter with offline-first RTI backend abstraction."""

    _SUPPORTED_RTI_TYPES = {"certi", "pitch", "mak", "stub"}

    def __init__(self, config: dict):
        self.config = dict(config or {})
        requested_mode = (
            os.getenv("S3M_HLA_RTI_TYPE")
            or str(self.config.get("rti_type", "stub"))
            or "stub"
        ).strip().lower()
        self.requested_mode = requested_mode if requested_mode in self._SUPPORTED_RTI_TYPES else "stub"
        self.mode = "stub"
        self.rti_host = os.getenv("S3M_HLA_RTI_HOST", str(self.config.get("rti_host", "localhost")))
        self.rti_port = int(os.getenv("S3M_HLA_RTI_PORT", str(self.config.get("rti_port", 11000))))
        self.time_step = float(self.config.get("time_step_seconds", 0.1))
        if self.time_step <= 0:
            self.time_step = 0.1
        self.federation_name = str(self.config.get("federation_name", ""))
        self.fom_path = str(self.config.get("fom_path", "configs/interop/s3m_fom.xml"))
        self.joined = False
        self._objects_published = 0
        self._objects_received = 0
        self._reflect_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._interaction_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._reflected_objects: List[Dict[str, Any]] = []
        self._received_interactions: List[Dict[str, Any]] = []
        self._converter = DISCoordinateConverter()
        self._last_error = ""
        self._fallback_reason = ""

        # Tactical interoperability note: non-stub adapters are intentionally routed
        # through stub until coalition RTI C-library bindings are installed.
        self._backend: RTIBackend = HLAStubRTI(time_step=self.time_step)
        if self.requested_mode != "stub":
            self._fallback_reason = (
                f"{self.requested_mode} backend unavailable in this deployment; using deterministic stub mode"
            )
        self._backend.register_object_callback(self._on_object_reflected)
        self._backend.register_interaction_callback(self._on_interaction_received)

    def create_federation(self, name: str, fom_path: str) -> bool:
        if not str(name).strip():
            self._last_error = "federation name is required"
            return False
        resolved_fom = self._resolve_fom_path(fom_path)
        if resolved_fom is None:
            self._last_error = f"FOM path not found: {fom_path}"
            return False
        try:
            ElementTree.parse(resolved_fom)
        except ElementTree.ParseError as exc:
            self._last_error = f"invalid FOM XML: {exc}"
            return False

        ok = self._backend.create_federation(str(name).strip(), str(resolved_fom))
        if ok:
            self.federation_name = str(name).strip()
            self.fom_path = str(resolved_fom)
        else:
            self._last_error = "backend rejected federation creation"
        return ok

    def join_federation(self, name: str) -> bool:
        if not str(name).strip():
            self._last_error = "federation name is required"
            return False
        ok = self._backend.join_federation(str(name).strip())
        self.joined = bool(ok)
        if not ok:
            self._last_error = f"failed to join federation: {name}"
        return ok

    def publish_object_class(self, class_name: str, attributes: List[str]) -> bool:
        if not isinstance(attributes, list):
            self._last_error = "attributes must be a list"
            return False
        ok = self._backend.publish_object_class(str(class_name), [str(attr) for attr in attributes])
        if not ok:
            self._last_error = f"failed to publish class {class_name}"
        return ok

    def subscribe_object_class(self, class_name: str, attributes: List[str]) -> bool:
        if not isinstance(attributes, list):
            self._last_error = "attributes must be a list"
            return False
        ok = self._backend.subscribe_object_class(str(class_name), [str(attr) for attr in attributes])
        if not ok:
            self._last_error = f"failed to subscribe class {class_name}"
        return ok

    def update_object(self, class_name: str, object_handle: int, attributes: Dict[str, Any]) -> bool:
        if not isinstance(attributes, dict):
            self._last_error = "attributes must be a dictionary"
            return False
        normalized = self._normalize_attributes(attributes)
        ok = self._backend.update_object(str(class_name), int(object_handle), normalized)
        if ok:
            self._objects_published += 1
            return True
        self._last_error = f"failed to update object for class {class_name}"
        return False

    def reflect_object(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._reflect_callbacks.append(callback)

    def send_interaction(self, class_name: str, parameters: Dict[str, Any]) -> bool:
        if not isinstance(parameters, dict):
            self._last_error = "interaction parameters must be a dictionary"
            return False
        ok = self._backend.send_interaction(str(class_name), dict(parameters))
        if not ok:
            self._last_error = f"failed to send interaction {class_name}"
        return ok

    def receive_interaction(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._interaction_callbacks.append(callback)

    def resign_federation(self) -> bool:
        ok = self._backend.resign_federation()
        if ok:
            self.joined = False
        else:
            self._last_error = "failed to resign federation"
        return ok

    def destroy_federation(self, name: str) -> bool:
        ok = self._backend.destroy_federation(str(name).strip())
        if not ok:
            self._last_error = f"failed to destroy federation: {name}"
            return False
        self.joined = False
        self.federation_name = ""
        return True

    def advance_time(self, step: float) -> bool:
        requested_step = float(step)
        if requested_step <= 0:
            requested_step = self.time_step
        ok = self._backend.advance_time(requested_step)
        if not ok:
            self._last_error = f"invalid time step: {step}"
        return ok

    def get_federation_status(self) -> dict:
        return {
            "mode": self.mode,
            "federation_name": self.federation_name,
            "joined": self.joined,
            "objects_published": self._objects_published,
            "objects_received": self._objects_received,
            "time_step": self.time_step,
            "requested_mode": self.requested_mode,
            "fallback_reason": self._fallback_reason,
        }

    def health_check(self) -> dict:
        backend = self._backend.health_check()
        return {
            "status": "operational" if self.joined or self.federation_name else "standby",
            "adapter": self.get_federation_status(),
            "backend": backend,
            "last_error": self._last_error,
            "objects_cached": len(self._reflected_objects),
            "interactions_cached": len(self._received_interactions),
        }

    def get_objects(self) -> List[Dict[str, Any]]:
        return self._backend.get_objects()

    def get_interactions(self) -> List[Dict[str, Any]]:
        return self._backend.get_interactions()

    def _resolve_fom_path(self, fom_path: str) -> Path | None:
        candidate = Path(str(fom_path).strip())
        if candidate.is_absolute():
            return candidate if candidate.exists() else None
        cwd_resolved = (Path.cwd() / candidate).resolve()
        if cwd_resolved.exists():
            return cwd_resolved
        repo_resolved = (Path(__file__).resolve().parents[3] / candidate).resolve()
        if repo_resolved.exists():
            return repo_resolved
        return None

    def _normalize_attributes(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in attributes.items():
            key_name = str(key)
            lower = key_name.lower()
            if lower == "position":
                normalized["Position"] = self._encode_position(value)
            elif lower == "velocity":
                normalized["Velocity"] = self._encode_velocity(value)
            elif lower == "marking":
                normalized["Marking"] = str(value)
            else:
                normalized[key_name] = value
        return normalized

    def _encode_position(self, value: Any) -> str:
        lat = 0.0
        lon = 0.0
        alt = 0.0
        if isinstance(value, str):
            return value
        if isinstance(value, DISWorldCoordinate):
            lat, lon, alt = self._converter.dis_to_lla(value)
        elif isinstance(value, dict):
            if {"x", "y", "z"}.issubset(value.keys()):
                lat, lon, alt = self._converter.ecef_to_lla(
                    float(value.get("x", 0.0)),
                    float(value.get("y", 0.0)),
                    float(value.get("z", 0.0)),
                )
            else:
                lat = self._safe_float(value.get("lat", value.get("latitude", 0.0)))
                lon = self._safe_float(value.get("lon", value.get("longitude", 0.0)))
                alt = self._safe_float(value.get("alt", value.get("altitude", 0.0)))
        elif isinstance(value, (list, tuple)) and len(value) >= 3:
            lat = self._safe_float(value[0])
            lon = self._safe_float(value[1])
            alt = self._safe_float(value[2])
        return f"{lat:.6f},{lon:.6f},{alt:.2f}"

    @staticmethod
    def _encode_velocity(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            x = float(value.get("x", value.get("vx", 0.0)))
            y = float(value.get("y", value.get("vy", 0.0)))
            z = float(value.get("z", value.get("vz", 0.0)))
            return f"{x:.3f},{y:.3f},{z:.3f}"
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return f"{float(value[0]):.3f},{float(value[1]):.3f},{float(value[2]):.3f}"
        return "0.000,0.000,0.000"

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _on_object_reflected(self, payload: Dict[str, Any]) -> None:
        self._objects_received += 1
        self._reflected_objects.append(dict(payload))
        if len(self._reflected_objects) > 1000:
            self._reflected_objects = self._reflected_objects[-1000:]
        for callback in list(self._reflect_callbacks):
            callback(dict(payload))

    def _on_interaction_received(self, payload: Dict[str, Any]) -> None:
        self._received_interactions.append(dict(payload))
        if len(self._received_interactions) > 1000:
            self._received_interactions = self._received_interactions[-1000:]
        for callback in list(self._interaction_callbacks):
            callback(dict(payload))
