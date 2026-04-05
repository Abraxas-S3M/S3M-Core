"""Safety and governance controls for tactical platform actuation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
import hashlib
import secrets
from typing import Any, Iterable

try:  # Dependency is optional in this repository snapshot.
    from src.platforms.common.messages import PlatformCommandMessage
except Exception:  # pragma: no cover - exercised only when dependency is absent.
    PlatformCommandMessage = Any  # type: ignore[misc,assignment]


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class AuthorityLevel(IntEnum):
    """Escalating command authority in the tactical chain of command."""

    OBSERVER = 1
    OPERATOR = 2
    WEAPONS_OFFICER = 3
    MISSION_COMMANDER = 4

    @classmethod
    def from_value(cls, value: "AuthorityLevel | str | int") -> "AuthorityLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            candidate = value.strip().upper()
            return cls[candidate]
        return cls(int(value))


@dataclass(frozen=True)
class OperatorRecord:
    operator_id: str
    display_name: str
    authority_level: AuthorityLevel
    registered_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenRecord:
    token_id: str
    operator_id: str
    purpose: str
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False

    @property
    def is_expired(self) -> bool:
        return _utc_now() >= self.expires_at


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor_id: str
    outcome: str
    detail: str
    timestamp: datetime


class ControlAuthorityService:
    """Registers operators, mints control tokens, and records governance audits."""

    def __init__(self, token_ttl_seconds: int = 3600) -> None:
        if token_ttl_seconds <= 0:
            raise ValueError("token_ttl_seconds must be positive")
        self._token_ttl_seconds = token_ttl_seconds
        self._operators: dict[str, OperatorRecord] = {}
        self._tokens: dict[str, TokenRecord] = {}
        self._audit_trail: list[AuditEvent] = []

    @staticmethod
    def validate_authority_level(
        granted_level: AuthorityLevel | str | int,
        required_level: AuthorityLevel | str | int,
    ) -> bool:
        granted = AuthorityLevel.from_value(granted_level)
        required = AuthorityLevel.from_value(required_level)
        return granted >= required

    def register_operator(
        self,
        operator_id: str,
        display_name: str,
        authority_level: AuthorityLevel | str | int,
        metadata: dict[str, str] | None = None,
    ) -> OperatorRecord:
        operator_id = self._validate_identifier(operator_id, "operator_id")
        display_name = self._validate_identifier(display_name, "display_name")
        parsed_level = AuthorityLevel.from_value(authority_level)
        record = OperatorRecord(
            operator_id=operator_id,
            display_name=display_name,
            authority_level=parsed_level,
            registered_at=_utc_now(),
            metadata=dict(metadata or {}),
        )
        self._operators[operator_id] = record
        self._audit("REGISTER_OPERATOR", operator_id, "SUCCESS", f"level={parsed_level.name}")
        return record

    def issue_authorization_token(self, operator_id: str, purpose: str = "actuation") -> str:
        operator_id = self._validate_identifier(operator_id, "operator_id")
        purpose = self._validate_identifier(purpose, "purpose")
        if operator_id not in self._operators:
            self._audit("ISSUE_TOKEN", operator_id, "DENIED", "operator_not_registered")
            raise PermissionError("operator is not registered")

        raw_token = secrets.token_urlsafe(32)
        token_digest = self._digest_token(raw_token)
        issued_at = _utc_now()
        self._tokens[token_digest] = TokenRecord(
            token_id=token_digest[:12],
            operator_id=operator_id,
            purpose=purpose,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(seconds=self._token_ttl_seconds),
            revoked=False,
        )
        self._audit("ISSUE_TOKEN", operator_id, "SUCCESS", f"purpose={purpose}")
        return raw_token

    def issue_token(self, operator_id: str, purpose: str = "actuation") -> str:
        return self.issue_authorization_token(operator_id=operator_id, purpose=purpose)

    def revoke_authorization_token(self, token: str, reason: str = "manual_revocation") -> None:
        token_digest = self._digest_token(token)
        existing = self._tokens.get(token_digest)
        if not existing:
            self._audit("REVOKE_TOKEN", "UNKNOWN", "DENIED", "token_not_found")
            raise PermissionError("token is not recognized")
        self._tokens[token_digest] = TokenRecord(
            token_id=existing.token_id,
            operator_id=existing.operator_id,
            purpose=existing.purpose,
            issued_at=existing.issued_at,
            expires_at=existing.expires_at,
            revoked=True,
        )
        self._audit("REVOKE_TOKEN", existing.operator_id, "SUCCESS", reason)

    def revoke_token(self, token: str, reason: str = "manual_revocation") -> None:
        self.revoke_authorization_token(token=token, reason=reason)

    def validate_authorization(
        self,
        token: str,
        required_level: AuthorityLevel | str | int = AuthorityLevel.OBSERVER,
        required_purpose: str | None = None,
    ) -> bool:
        try:
            self.assert_authorized(
                token=token,
                required_level=required_level,
                required_purpose=required_purpose,
            )
            return True
        except PermissionError:
            return False

    def validate_token(
        self,
        token: str,
        required_level: AuthorityLevel | str | int = AuthorityLevel.OBSERVER,
        required_purpose: str | None = None,
    ) -> bool:
        return self.validate_authorization(
            token=token,
            required_level=required_level,
            required_purpose=required_purpose,
        )

    def assert_authorized(
        self,
        token: str,
        required_level: AuthorityLevel | str | int = AuthorityLevel.OBSERVER,
        required_purpose: str | None = None,
    ) -> TokenRecord:
        required = AuthorityLevel.from_value(required_level)
        token_digest = self._digest_token(token)
        record = self._tokens.get(token_digest)
        if record is None:
            self._audit("AUTHORIZE", "UNKNOWN", "DENIED", "token_not_found")
            raise PermissionError("token is not recognized")
        if record.revoked:
            self._audit("AUTHORIZE", record.operator_id, "DENIED", "token_revoked")
            raise PermissionError("token has been revoked")
        if record.is_expired:
            self._audit("AUTHORIZE", record.operator_id, "DENIED", "token_expired")
            raise PermissionError("token has expired")
        if required_purpose and record.purpose != required_purpose:
            self._audit("AUTHORIZE", record.operator_id, "DENIED", "purpose_mismatch")
            raise PermissionError("token purpose does not match requested action")

        operator = self._operators.get(record.operator_id)
        if operator is None:
            self._audit("AUTHORIZE", record.operator_id, "DENIED", "operator_not_registered")
            raise PermissionError("operator is no longer registered")
        if not self.validate_authority_level(operator.authority_level, required):
            self._audit(
                "AUTHORIZE",
                operator.operator_id,
                "DENIED",
                f"required={required.name};actual={operator.authority_level.name}",
            )
            raise PermissionError("insufficient authority level")

        self._audit("AUTHORIZE", operator.operator_id, "SUCCESS", f"required={required.name}")
        return record

    def has_authority(
        self,
        operator_id: str,
        required_level: AuthorityLevel | str | int,
    ) -> bool:
        operator = self._operators.get(operator_id)
        if operator is None:
            return False
        return self.validate_authority_level(operator.authority_level, required_level)

    def record_external_audit_event(
        self,
        event_type: str,
        actor_id: str,
        outcome: str,
        detail: str,
    ) -> None:
        self._audit(event_type, actor_id, outcome, detail)

    def get_operator(self, operator_id: str) -> OperatorRecord | None:
        return self._operators.get(operator_id)

    def get_audit_trail(self, limit: int | None = None) -> list[AuditEvent]:
        if limit is None:
            return list(self._audit_trail)
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if limit == 0:
            return []
        return self._audit_trail[-limit:]

    @staticmethod
    def _digest_token(raw_token: str) -> str:
        if not raw_token or not raw_token.strip():
            raise PermissionError("token is required")
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_identifier(value: str, field_name: str) -> str:
        cleaned = value.strip() if isinstance(value, str) else ""
        if not cleaned:
            raise ValueError(f"{field_name} must be non-empty")
        if len(cleaned) > 128:
            raise ValueError(f"{field_name} must be <= 128 characters")
        return cleaned

    def _audit(self, event_type: str, actor_id: str, outcome: str, detail: str) -> None:
        self._audit_trail.append(
            AuditEvent(
                event_type=event_type,
                actor_id=actor_id,
                outcome=outcome,
                detail=detail,
                timestamp=_utc_now(),
            )
        )


class InterlockState(str, Enum):
    SAFE = "SAFE"
    ARMED = "ARMED"
    FIRING = "FIRING"

    @classmethod
    def from_value(cls, value: "InterlockState | str") -> "InterlockState":
        if isinstance(value, cls):
            return value
        candidate = value.strip().upper()
        if candidate in cls.__members__:
            return cls[candidate]
        return cls(candidate)


@dataclass(frozen=True)
class FaultRecord:
    fault_code: str
    description: str
    created_at: datetime


@dataclass(frozen=True)
class InterlockEvent:
    from_state: InterlockState
    to_state: InterlockState
    actor_id: str
    reason: str
    timestamp: datetime


class InterlockStateMachine:
    """Authorization-gated interlock for SAFE/ARMED/FIRING weapon release states."""

    def __init__(self, authority_service: ControlAuthorityService) -> None:
        self._authority_service = authority_service
        self._state = InterlockState.SAFE
        self._fault: FaultRecord | None = None
        self._emergency_stop_latched = False
        self._events: list[InterlockEvent] = []
        self._required_levels: dict[tuple[InterlockState, InterlockState], AuthorityLevel] = {
            (InterlockState.SAFE, InterlockState.ARMED): AuthorityLevel.WEAPONS_OFFICER,
            (InterlockState.ARMED, InterlockState.FIRING): AuthorityLevel.MISSION_COMMANDER,
            (InterlockState.FIRING, InterlockState.ARMED): AuthorityLevel.WEAPONS_OFFICER,
            (InterlockState.ARMED, InterlockState.SAFE): AuthorityLevel.OPERATOR,
            (InterlockState.FIRING, InterlockState.SAFE): AuthorityLevel.OPERATOR,
        }

    @property
    def state(self) -> InterlockState:
        return self._state

    @property
    def fault(self) -> FaultRecord | None:
        return self._fault

    @property
    def emergency_stop_latched(self) -> bool:
        return self._emergency_stop_latched

    def transition_to(
        self,
        target_state: InterlockState | str,
        token: str,
        reason: str = "",
    ) -> InterlockState:
        destination = InterlockState.from_value(target_state)
        if destination == self._state:
            return self._state
        required_level = self._required_levels.get((self._state, destination))
        if required_level is None:
            raise ValueError(f"invalid transition {self._state.value}->{destination.value}")

        token_record = self._authority_service.assert_authorized(token, required_level)
        if self._emergency_stop_latched and destination != InterlockState.SAFE:
            raise PermissionError("emergency stop latch blocks non-SAFE transitions")
        if self._fault is not None and destination != InterlockState.SAFE:
            raise PermissionError("active fault blocks non-SAFE transitions")

        prior = self._state
        self._state = destination
        event = InterlockEvent(
            from_state=prior,
            to_state=destination,
            actor_id=token_record.operator_id,
            reason=reason.strip() or "state_transition",
            timestamp=_utc_now(),
        )
        self._events.append(event)
        self._authority_service.record_external_audit_event(
            event_type="INTERLOCK_TRANSITION",
            actor_id=token_record.operator_id,
            outcome="SUCCESS",
            detail=f"{prior.value}->{destination.value}",
        )
        return self._state

    def request_transition(
        self,
        target_state: InterlockState | str,
        token: str,
        reason: str = "",
    ) -> InterlockState:
        return self.transition_to(target_state=target_state, token=token, reason=reason)

    def emergency_stop(self, token: str, reason: str = "emergency_stop") -> None:
        token_record = self._authority_service.assert_authorized(token, AuthorityLevel.OPERATOR)
        # Tactical safety doctrine: e-stop always drops to SAFE immediately.
        prior = self._state
        self._state = InterlockState.SAFE
        self._emergency_stop_latched = True
        self._events.append(
            InterlockEvent(
                from_state=prior,
                to_state=InterlockState.SAFE,
                actor_id=token_record.operator_id,
                reason=reason,
                timestamp=_utc_now(),
            )
        )
        self._authority_service.record_external_audit_event(
            event_type="INTERLOCK_ESTOP",
            actor_id=token_record.operator_id,
            outcome="SUCCESS",
            detail=reason,
        )

    def reset_emergency_stop(self, token: str, reason: str = "reset_estop") -> None:
        token_record = self._authority_service.assert_authorized(token, AuthorityLevel.MISSION_COMMANDER)
        if self._fault is not None:
            raise PermissionError("cannot clear emergency stop while fault is active")
        self._emergency_stop_latched = False
        self._authority_service.record_external_audit_event(
            event_type="INTERLOCK_ESTOP_RESET",
            actor_id=token_record.operator_id,
            outcome="SUCCESS",
            detail=reason,
        )

    def report_fault(self, token: str, fault_code: str, description: str) -> FaultRecord:
        token_record = self._authority_service.assert_authorized(token, AuthorityLevel.OPERATOR)
        code = fault_code.strip()
        text = description.strip()
        if not code or not text:
            raise ValueError("fault_code and description are required")
        self._fault = FaultRecord(fault_code=code, description=text, created_at=_utc_now())
        self._state = InterlockState.SAFE
        self._authority_service.record_external_audit_event(
            event_type="INTERLOCK_FAULT",
            actor_id=token_record.operator_id,
            outcome="LATCHED",
            detail=code,
        )
        return self._fault

    def clear_fault(self, token: str, reason: str = "fault_cleared") -> None:
        token_record = self._authority_service.assert_authorized(token, AuthorityLevel.MISSION_COMMANDER)
        self._fault = None
        self._authority_service.record_external_audit_event(
            event_type="INTERLOCK_FAULT_CLEAR",
            actor_id=token_record.operator_id,
            outcome="SUCCESS",
            detail=reason,
        )

    def can_actuate(self) -> bool:
        return (
            self._state == InterlockState.FIRING
            and self._fault is None
            and not self._emergency_stop_latched
        )

    def get_history(self, limit: int | None = None) -> list[InterlockEvent]:
        if limit is None:
            return list(self._events)
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if limit == 0:
            return []
        return self._events[-limit:]


class SimMode(str, Enum):
    SIMULATION = "SIMULATION"
    LIVE = "LIVE"

    @classmethod
    def from_value(cls, value: "SimMode | str") -> "SimMode":
        if isinstance(value, cls):
            return value
        candidate = value.strip().upper()
        if candidate in cls.__members__:
            return cls[candidate]
        return cls(candidate)


@dataclass(frozen=True)
class ModeSwitchEvent:
    from_mode: SimMode
    to_mode: SimMode
    actor_id: str
    reason: str
    timestamp: datetime


class SimModeGuard:
    """Ensures simulation and live control planes remain strictly separated."""

    def __init__(
        self,
        authority_service: ControlAuthorityService,
        initial_mode: SimMode | str = SimMode.SIMULATION,
    ) -> None:
        self._authority_service = authority_service
        self._mode = SimMode.from_value(initial_mode)
        self._events: list[ModeSwitchEvent] = []

    @property
    def mode(self) -> SimMode:
        return self._mode

    def switch_mode(self, token: str, target_mode: SimMode | str, reason: str = "") -> SimMode:
        destination = SimMode.from_value(target_mode)
        if destination == self._mode:
            return self._mode
        token_record = self._authority_service.assert_authorized(
            token=token,
            required_level=AuthorityLevel.MISSION_COMMANDER,
        )
        prior = self._mode
        self._mode = destination
        event = ModeSwitchEvent(
            from_mode=prior,
            to_mode=destination,
            actor_id=token_record.operator_id,
            reason=reason.strip() or "mode_switch",
            timestamp=_utc_now(),
        )
        self._events.append(event)
        self._authority_service.record_external_audit_event(
            event_type="SIM_MODE_SWITCH",
            actor_id=token_record.operator_id,
            outcome="SUCCESS",
            detail=f"{prior.value}->{destination.value}",
        )
        return self._mode

    def assert_command_mode(self, simulated_command: bool) -> None:
        if simulated_command and self._mode != SimMode.SIMULATION:
            raise PermissionError("simulation command denied while in LIVE mode")
        if (not simulated_command) and self._mode != SimMode.LIVE:
            raise PermissionError("live command denied while in SIMULATION mode")

    def get_history(self, limit: int | None = None) -> list[ModeSwitchEvent]:
        if limit is None:
            return list(self._events)
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if limit == 0:
            return []
        return self._events[-limit:]


@dataclass(frozen=True)
class GeofenceZone:
    name: str
    polygon: tuple[tuple[float, float], ...]
    restricted: bool


@dataclass(frozen=True)
class RangeViolation:
    code: str
    detail: str
    timestamp: datetime


@dataclass(frozen=True)
class ComplianceReport:
    compliant: bool
    violations: tuple[RangeViolation, ...]
    timestamp: datetime


class RangeComplianceEngine:
    """Checks geofence, altitude, and speed constraints before release authority."""

    def __init__(
        self,
        min_altitude_m: float = 5.0,
        max_altitude_m: float = 120.0,
        max_speed_mps: float = 45.0,
    ) -> None:
        self._allowed_zones: dict[str, GeofenceZone] = {}
        self._restricted_zones: dict[str, GeofenceZone] = {}
        self._violation_log: list[RangeViolation] = []
        self.set_altitude_limits(min_altitude_m=min_altitude_m, max_altitude_m=max_altitude_m)
        self.set_speed_limit(max_speed_mps=max_speed_mps)

    def set_altitude_limits(self, min_altitude_m: float, max_altitude_m: float) -> None:
        if min_altitude_m < 0:
            raise ValueError("min_altitude_m cannot be negative")
        if max_altitude_m <= min_altitude_m:
            raise ValueError("max_altitude_m must be greater than min_altitude_m")
        self._min_altitude_m = float(min_altitude_m)
        self._max_altitude_m = float(max_altitude_m)

    def set_speed_limit(self, max_speed_mps: float) -> None:
        if max_speed_mps <= 0:
            raise ValueError("max_speed_mps must be positive")
        self._max_speed_mps = float(max_speed_mps)

    def add_allowed_zone(self, name: str, polygon: Iterable[tuple[float, float]]) -> None:
        zone = self._create_zone(name=name, polygon=polygon, restricted=False)
        self._allowed_zones[zone.name] = zone

    def add_restricted_zone(self, name: str, polygon: Iterable[tuple[float, float]]) -> None:
        zone = self._create_zone(name=name, polygon=polygon, restricted=True)
        self._restricted_zones[zone.name] = zone

    def clear_zones(self) -> None:
        self._allowed_zones.clear()
        self._restricted_zones.clear()

    def evaluate(
        self,
        latitude: float,
        longitude: float,
        altitude_m: float,
        speed_mps: float,
        context: str = "",
    ) -> ComplianceReport:
        lat = float(latitude)
        lon = float(longitude)
        alt = float(altitude_m)
        speed = float(speed_mps)
        violations: list[RangeViolation] = []

        if not (-90.0 <= lat <= 90.0):
            violations.append(self._new_violation("LATITUDE_RANGE", f"latitude={lat}"))
        if not (-180.0 <= lon <= 180.0):
            violations.append(self._new_violation("LONGITUDE_RANGE", f"longitude={lon}"))
        if alt < self._min_altitude_m or alt > self._max_altitude_m:
            violations.append(
                self._new_violation(
                    "ALTITUDE_LIMIT",
                    f"altitude={alt};allowed=[{self._min_altitude_m},{self._max_altitude_m}]",
                )
            )
        if speed > self._max_speed_mps:
            violations.append(
                self._new_violation("SPEED_LIMIT", f"speed={speed};max={self._max_speed_mps}")
            )

        point = (lat, lon)
        for zone in self._restricted_zones.values():
            if self._point_in_polygon(point=point, polygon=zone.polygon):
                violations.append(self._new_violation("RESTRICTED_ZONE", f"zone={zone.name}"))

        if self._allowed_zones:
            in_any_allowed = any(
                self._point_in_polygon(point=point, polygon=zone.polygon)
                for zone in self._allowed_zones.values()
            )
            if not in_any_allowed:
                suffix = f";context={context.strip()}" if context.strip() else ""
                violations.append(self._new_violation("OUTSIDE_ALLOWED_ZONE", f"none{suffix}"))

        report = ComplianceReport(
            compliant=len(violations) == 0,
            violations=tuple(violations),
            timestamp=_utc_now(),
        )
        self._violation_log.extend(violations)
        return report

    def evaluate_message(self, message: PlatformCommandMessage | Any) -> ComplianceReport:
        latitude = self._extract_numeric_field(message, ("latitude", "lat"))
        longitude = self._extract_numeric_field(message, ("longitude", "lon", "lng"))
        altitude = self._extract_numeric_field(message, ("altitude_m", "altitude"))
        speed = self._extract_numeric_field(message, ("speed_mps", "speed"))
        return self.evaluate(
            latitude=latitude,
            longitude=longitude,
            altitude_m=altitude,
            speed_mps=speed,
            context=message.__class__.__name__,
        )

    def get_violation_log(self, limit: int | None = None) -> list[RangeViolation]:
        if limit is None:
            return list(self._violation_log)
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if limit == 0:
            return []
        return self._violation_log[-limit:]

    @staticmethod
    def _extract_numeric_field(message: Any, field_names: tuple[str, ...]) -> float:
        for name in field_names:
            if hasattr(message, name):
                value = getattr(message, name)
                return float(value)
            if isinstance(message, dict) and name in message:
                return float(message[name])
        joined = ", ".join(field_names)
        raise ValueError(f"message missing numeric field; expected one of: {joined}")

    def _create_zone(
        self,
        name: str,
        polygon: Iterable[tuple[float, float]],
        restricted: bool,
    ) -> GeofenceZone:
        zone_name = name.strip()
        if not zone_name:
            raise ValueError("zone name must be non-empty")
        vertices = tuple((float(lat), float(lon)) for lat, lon in polygon)
        if len(vertices) < 3:
            raise ValueError("polygon must include at least 3 vertices")
        for lat, lon in vertices:
            if not (-90.0 <= lat <= 90.0):
                raise ValueError("polygon latitude must be between -90 and 90")
            if not (-180.0 <= lon <= 180.0):
                raise ValueError("polygon longitude must be between -180 and 180")
        return GeofenceZone(name=zone_name, polygon=vertices, restricted=restricted)

    def _new_violation(self, code: str, detail: str) -> RangeViolation:
        return RangeViolation(code=code, detail=detail, timestamp=_utc_now())

    @staticmethod
    def _point_in_polygon(
        point: tuple[float, float],
        polygon: tuple[tuple[float, float], ...],
    ) -> bool:
        """
        Ray-casting point-in-polygon using longitude as x-axis and latitude as y-axis.
        """
        y, x = point
        inside = False
        count = len(polygon)
        for i in range(count):
            y1, x1 = polygon[i]
            y2, x2 = polygon[(i + 1) % count]
            if RangeComplianceEngine._point_on_segment(y, x, y1, x1, y2, x2):
                return True
            if (x1 > x) == (x2 > x):
                continue
            denominator = (x2 - x1) if (x2 - x1) != 0 else 1e-12
            y_intersection = (y2 - y1) * (x - x1) / denominator + y1
            if y < y_intersection:
                inside = not inside
        return inside

    @staticmethod
    def _point_on_segment(
        y: float,
        x: float,
        y1: float,
        x1: float,
        y2: float,
        x2: float,
        epsilon: float = 1e-9,
    ) -> bool:
        if min(y1, y2) - epsilon <= y <= max(y1, y2) + epsilon and min(
            x1, x2
        ) - epsilon <= x <= max(x1, x2) + epsilon:
            cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
            return abs(cross) <= epsilon
        return False

