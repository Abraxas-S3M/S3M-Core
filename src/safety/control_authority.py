"""Control authority and safety interlocks for tactical weapon release.

This module enforces command authorization, safe arming state progression, and
geofence compliance before kinetic actions are permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import uuid

from src.platforms.common import (
    AuthorizationType,
    AuthorityLevel,
    InterlockState,
    OperatorAuthorization,
)


@dataclass
class AuthorizationRecord:
    """Issued authorization token with expiry and revocation metadata."""

    auth_id: str
    operator_id: str
    auth_type: AuthorizationType
    expires_at: datetime
    revoked: bool = False


class ControlAuthorityService:
    """Authority service that issues and validates operator action tokens."""

    def __init__(self) -> None:
        self._operators: dict[str, AuthorityLevel] = {}
        self._authorizations: dict[str, AuthorizationRecord] = {}

    def register_operator(self, operator_id: str, level: AuthorityLevel) -> None:
        if not operator_id:
            raise ValueError("operator_id must be a non-empty string")
        self._operators[operator_id] = level

    def issue_authorization(
        self,
        operator_id: str,
        auth_type: AuthorizationType,
        ttl_seconds: int = 300,
    ) -> OperatorAuthorization:
        if operator_id not in self._operators:
            raise ValueError("operator is not registered")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")

        auth = OperatorAuthorization(operator_id=operator_id, auth_type=auth_type, auth_id=str(uuid.uuid4()))
        self._authorizations[auth.auth_id] = AuthorizationRecord(
            auth_id=auth.auth_id,
            operator_id=operator_id,
            auth_type=auth_type,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        return auth

    def validate_authorization(self, auth_id: str) -> bool:
        record = self._authorizations.get(auth_id)
        if record is None:
            return False
        if record.revoked:
            return False
        return datetime.now(timezone.utc) <= record.expires_at

    def revoke_authorization(self, auth_id: str) -> None:
        record = self._authorizations.get(auth_id)
        if record is not None:
            record.revoked = True


class InterlockStateMachine:
    """Safety FSM enforcing SAFE→ARMED→FIRING sequencing under authorization."""

    def __init__(self, payload_id: str) -> None:
        self.payload_id = payload_id
        self.state = InterlockState.SAFE

    def transition(self, requested_state: InterlockState, auth: OperatorAuthorization | None = None) -> bool:
        if requested_state == self.state:
            return True
        if requested_state == InterlockState.SAFE:
            self.state = InterlockState.SAFE
            return True
        if self.state == InterlockState.SAFE and requested_state == InterlockState.ARMED:
            if not self._valid_engage_auth(auth):
                return False
            self.state = InterlockState.ARMED
            return True
        if self.state == InterlockState.ARMED and requested_state == InterlockState.FIRING:
            if not self._valid_engage_auth(auth):
                return False
            self.state = InterlockState.FIRING
            return True
        if self.state == InterlockState.FIRING and requested_state == InterlockState.ARMED:
            self.state = InterlockState.ARMED
            return True
        return False

    def emergency_stop(self) -> None:
        self.state = InterlockState.SAFE

    @staticmethod
    def _valid_engage_auth(auth: OperatorAuthorization | None) -> bool:
        return auth is not None and auth.auth_type == AuthorizationType.ENGAGE


@dataclass
class SimModeGuard:
    """Simulation mode guard to block live-fire actions during training."""

    simulation_mode: bool = False
    reason: str = field(default="live")

    def can_engage(self) -> bool:
        return not self.simulation_mode


class RangeComplianceEngine:
    """Geofence compliance engine for battlefield spatial safety controls."""

    def __init__(self) -> None:
        self._geofences: dict[str, tuple[list[tuple[float, float]], str]] = {}

    def add_geofence(self, geofence_id: str, polygon_xy: list[tuple[float, float]], policy: str) -> None:
        if policy not in {"allowed", "forbidden"}:
            raise ValueError("policy must be 'allowed' or 'forbidden'")
        if len(polygon_xy) < 3:
            raise ValueError("polygon must have at least 3 points")
        self._geofences[geofence_id] = (polygon_xy, policy)

    def check_position(self, platform_id: str, position: tuple[float, float, float]) -> bool:
        del platform_id  # kept for audit extension compatibility
        x, y, _ = position

        in_forbidden = False
        in_allowed = False
        has_allowed_zone = False
        for polygon, policy in self._geofences.values():
            inside = self._point_in_polygon(x, y, polygon)
            if policy == "forbidden" and inside:
                in_forbidden = True
            if policy == "allowed":
                has_allowed_zone = True
                if inside:
                    in_allowed = True

        if in_forbidden:
            return False
        if has_allowed_zone:
            return in_allowed
        return True

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
        """Ray-casting point-in-polygon check for geofence enforcement."""
        inside = False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside
