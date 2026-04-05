"""FastAPI routes for tactical platform adapter integration.

These routes provide a common control plane for platform and payload adapters
so operators can issue consistent commands across mixed-domain missions.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from src.api.platform_models import (
    CommandDispatchResponse,
    MobilityCommandRequest,
    PayloadStateResponse,
    PlatformCapabilitiesResponse,
    PlatformHealthResponse,
    PlatformOperationResponse,
    PlatformStateEnvelope,
    PlatformStateResponse,
    SafeStateRequest,
    SensorCommandRequest,
)
from src.platforms.common.messages import MobilityCommand as MobilityCommandMessage
from src.platforms.fixed.horizon_adapter import HorizonAdapter
from src.platforms.payloads.weapon_adapters import (
    MANPADSAdapter,
    OrionZU23Adapter,
    RCWS127Adapter,
    SICHAdapter,
)
from src.platforms.uav.warwar_adapter import WarWarAdapter
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.platforms.usv.g24_adapter import G24Adapter

platform_router = APIRouter()

_MOBILITY_METHODS = ("apply_mobility_command", "apply_mobility")
_SENSOR_METHODS = ("apply_sensor_command", "apply_sensor")
_SAFE_STATE_METHODS = ("safe_state", "enter_safe_state")

_PLATFORM_BOOTSTRAP = (
    ("hmmwv-001", lambda platform_id: HMMWVAdapter(platform_id), "ugv"),
    ("warwar-001", lambda platform_id: WarWarAdapter(platform_id), "uav"),
    ("g24-001", lambda platform_id: G24Adapter(platform_id), "usv"),
    ("horizon-001", lambda platform_id: HorizonAdapter(platform_id), "fixed"),
    ("rcws127-001", lambda platform_id: RCWS127Adapter(platform_id), "payload"),
    ("sich-001", lambda platform_id: SICHAdapter(platform_id), "payload"),
    ("orion-001", lambda platform_id: OrionZU23Adapter(platform_id), "payload"),
    ("manpads-001", lambda platform_id: MANPADSAdapter(platform_id), "payload"),
)


class PlatformRegistry:
    """Singleton registry for instantiated platform and payload adapters."""

    _instance: PlatformRegistry | None = None
    _instance_lock = Lock()

    def __new__(cls) -> PlatformRegistry:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._adapters: dict[str, Any] = {}
                    cls._instance._metadata: dict[str, dict[str, Any]] = {}
                    cls._instance._lock = Lock()
        return cls._instance

    def register(self, platform_id: str, adapter: Any, *, domain: str) -> None:
        if not platform_id or not isinstance(platform_id, str):
            raise ValueError("platform_id must be a non-empty string")
        with self._lock:
            self._adapters[platform_id] = adapter
            self._metadata[platform_id] = {
                "domain": domain,
                "adapter_class": adapter.__class__.__name__,
            }

    def get(self, platform_id: str) -> Any | None:
        return self._adapters.get(platform_id)

    def require(self, platform_id: str) -> Any:
        adapter = self.get(platform_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"Unknown platform_id: {platform_id}")
        return adapter

    def metadata(self, platform_id: str) -> dict[str, Any]:
        return dict(self._metadata.get(platform_id, {}))


platform_registry = PlatformRegistry()


def _bootstrap_platforms() -> None:
    for platform_id, factory, domain in _PLATFORM_BOOTSTRAP:
        if platform_registry.get(platform_id) is None:
            platform_registry.register(platform_id, factory(platform_id), domain=domain)


def _connected_state(adapter: Any) -> bool | None:
    raw = getattr(adapter, "_connected", None)
    if isinstance(raw, bool):
        return raw
    return None


def _supports(adapter: Any, method_names: tuple[str, ...]) -> bool:
    return any(callable(getattr(adapter, method_name, None)) for method_name in method_names)


def _supported_operations(adapter: Any) -> list[str]:
    operations = ["connect", "disconnect", "state", "health", "capabilities", "safe-state"]
    if _supports(adapter, _MOBILITY_METHODS):
        operations.append("mobility")
    if _supports(adapter, _SENSOR_METHODS):
        operations.append("sensor")
    return operations


def _normalize_data(payload: Any) -> dict[str, Any]:
    encoded = jsonable_encoder(payload)
    if isinstance(encoded, dict):
        return encoded
    return {"result": encoded}


def _read_state(adapter: Any) -> Any:
    method = getattr(adapter, "read_state", None)
    if not callable(method):
        raise HTTPException(status_code=501, detail="Adapter does not implement read_state()")
    return method()


def _state_envelope(platform_id: str, state: Any) -> PlatformStateEnvelope:
    encoded = jsonable_encoder(asdict(state) if is_dataclass(state) else state)
    if not isinstance(encoded, dict):
        return PlatformStateEnvelope(platform_id=platform_id, state_type="raw", raw_state={"value": encoded})

    if {"platform_id", "platform_type", "position"}.issubset(encoded):
        return PlatformStateEnvelope(
            platform_id=platform_id,
            state_type="platform",
            platform_state=PlatformStateResponse.model_validate(encoded),
        )

    if {"payload_id", "ammo_count", "connected"}.issubset(encoded):
        return PlatformStateEnvelope(
            platform_id=platform_id,
            state_type="payload",
            payload_state=PayloadStateResponse.model_validate(encoded),
        )

    return PlatformStateEnvelope(platform_id=platform_id, state_type="raw", raw_state=encoded)


def _dispatch_command(
    *,
    adapter: Any,
    platform_id: str,
    command_name: Literal["mobility", "sensor", "safe-state"],
    method_names: tuple[str, ...],
    command_payload: dict[str, Any],
    alt_payload: Any | None = None,
) -> CommandDispatchResponse:
    for method_name in method_names:
        method = getattr(adapter, method_name, None)
        if not callable(method):
            continue
        try:
            result = method(command_payload)
        except TypeError:
            if alt_payload is None:
                return CommandDispatchResponse(
                    platform_id=platform_id,
                    command=command_name,
                    accepted=False,
                    detail=f"{method_name} rejected command payload shape",
                    data={"method": method_name},
                )
            result = method(alt_payload)
        except Exception as exc:
            return CommandDispatchResponse(
                platform_id=platform_id,
                command=command_name,
                accepted=False,
                detail=f"{method_name} failed: {exc}",
                data={"method": method_name},
            )
        return CommandDispatchResponse(
            platform_id=platform_id,
            command=command_name,
            accepted=True,
            detail=f"Command accepted via {method_name}",
            data={"method": method_name, "result": _normalize_data(result)},
        )

    return CommandDispatchResponse(
        platform_id=platform_id,
        command=command_name,
        accepted=False,
        detail=f"Adapter does not support {command_name} commands",
        data={},
    )


_bootstrap_platforms()


@platform_router.post("/api/platforms/{platform_id}/connect", response_model=PlatformOperationResponse)
async def connect_platform(platform_id: str) -> PlatformOperationResponse:
    adapter = platform_registry.require(platform_id)
    method = getattr(adapter, "connect", None)
    if not callable(method):
        raise HTTPException(status_code=501, detail="Adapter does not implement connect()")
    success = bool(method())
    return PlatformOperationResponse(
        platform_id=platform_id,
        operation="connect",
        success=success,
        connected=_connected_state(adapter),
        detail="Platform command link established" if success else "Connect rejected by adapter",
    )


@platform_router.post("/api/platforms/{platform_id}/disconnect", response_model=PlatformOperationResponse)
async def disconnect_platform(platform_id: str) -> PlatformOperationResponse:
    adapter = platform_registry.require(platform_id)
    method = getattr(adapter, "disconnect", None)
    if callable(method):
        success = bool(method())
    elif isinstance(getattr(adapter, "_connected", None), bool):
        setattr(adapter, "_connected", False)
        success = True
    else:
        success = False
    return PlatformOperationResponse(
        platform_id=platform_id,
        operation="disconnect",
        success=success,
        connected=_connected_state(adapter),
        detail="Platform command link closed" if success else "Disconnect unsupported by adapter",
    )


@platform_router.get("/api/platforms/{platform_id}/state", response_model=PlatformStateEnvelope)
async def get_platform_state(platform_id: str) -> PlatformStateEnvelope:
    adapter = platform_registry.require(platform_id)
    state = _read_state(adapter)
    return _state_envelope(platform_id, state)


@platform_router.get("/api/platforms/{platform_id}/health", response_model=PlatformHealthResponse)
async def get_platform_health(platform_id: str) -> PlatformHealthResponse:
    adapter = platform_registry.require(platform_id)
    connected = _connected_state(adapter)
    status = "connected" if connected else "disconnected" if connected is not None else "unknown"
    diagnostics = {
        "supported_operations": _supported_operations(adapter),
        "last_health_check_utc": datetime.now(timezone.utc).isoformat(),
    }
    return PlatformHealthResponse(
        platform_id=platform_id,
        adapter_class=adapter.__class__.__name__,
        status=status,
        connected=connected,
        diagnostics=diagnostics,
    )


@platform_router.post("/api/platforms/{platform_id}/mobility", response_model=CommandDispatchResponse)
async def send_mobility_command(platform_id: str, command: MobilityCommandRequest) -> CommandDispatchResponse:
    adapter = platform_registry.require(platform_id)
    payload = command.model_dump(mode="python")
    mobility_msg = MobilityCommandMessage(
        command_type=command.command_type,
        target_position=command.target_position,
    )
    return _dispatch_command(
        adapter=adapter,
        platform_id=platform_id,
        command_name="mobility",
        method_names=_MOBILITY_METHODS,
        command_payload=payload,
        alt_payload=mobility_msg,
    )


@platform_router.post("/api/platforms/{platform_id}/sensor", response_model=CommandDispatchResponse)
async def send_sensor_command(platform_id: str, command: SensorCommandRequest) -> CommandDispatchResponse:
    adapter = platform_registry.require(platform_id)
    payload = command.model_dump(mode="python")
    return _dispatch_command(
        adapter=adapter,
        platform_id=platform_id,
        command_name="sensor",
        method_names=_SENSOR_METHODS,
        command_payload=payload,
    )


@platform_router.post("/api/platforms/{platform_id}/safe-state", response_model=CommandDispatchResponse)
async def enter_safe_state(platform_id: str, request: SafeStateRequest | None = None) -> CommandDispatchResponse:
    adapter = platform_registry.require(platform_id)
    reason = request.reason if request is not None else "operator_request"
    for method_name in _SAFE_STATE_METHODS:
        method = getattr(adapter, method_name, None)
        if not callable(method):
            continue
        try:
            result = method(reason=reason)
        except TypeError:
            result = method(reason)
        except Exception as exc:
            return CommandDispatchResponse(
                platform_id=platform_id,
                command="safe-state",
                accepted=False,
                detail=f"{method_name} failed: {exc}",
                data={"method": method_name},
            )
        return CommandDispatchResponse(
            platform_id=platform_id,
            command="safe-state",
            accepted=True,
            detail=f"Safe-state executed via {method_name}",
            data={"method": method_name, "result": _normalize_data(result)},
        )

    # Tactical fallback: quiesce adapter link if explicit safe-state routine is unavailable.
    if isinstance(getattr(adapter, "_connected", None), bool):
        setattr(adapter, "_connected", False)
    return CommandDispatchResponse(
        platform_id=platform_id,
        command="safe-state",
        accepted=True,
        detail="Fallback safe-state engaged by quiescing command link",
        data={"reason": reason},
    )


@platform_router.get("/api/platforms/{platform_id}/capabilities", response_model=PlatformCapabilitiesResponse)
async def get_platform_capabilities(platform_id: str) -> PlatformCapabilitiesResponse:
    adapter = platform_registry.require(platform_id)
    meta = platform_registry.metadata(platform_id)
    return PlatformCapabilitiesResponse(
        platform_id=platform_id,
        adapter_class=meta.get("adapter_class", adapter.__class__.__name__),
        domain=meta.get("domain", "unknown"),
        supported_operations=_supported_operations(adapter),
        governance={
            "offline_only": True,
            "external_api_calls_allowed": False,
            "edge_target": "nvidia-jetson-agx-orin",
        },
    )
