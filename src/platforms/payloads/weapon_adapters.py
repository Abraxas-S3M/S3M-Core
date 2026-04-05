"""Supervised weapon payload adapters for Abraxas platform systems.

Every engagement path in this module requires explicit operator authorization.
Autonomous fire-release is intentionally locked out at this layer.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import cos, radians
from typing import Deque, Protocol, runtime_checkable


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class OperatorAuthorization:
    """Operator-issued command authorization token for supervised effects."""

    operator_id: str
    authorized_actions: frozenset[str]
    issued_at: datetime = field(default_factory=_utc_now)
    expires_at: datetime = field(default_factory=_utc_now)
    command_nonce: str | None = None

    def allows(self, action: str, now: datetime | None = None) -> bool:
        """Return True when action is explicitly permitted and unexpired."""
        now = now or _utc_now()
        return now <= self.expires_at and action in self.authorized_actions


@dataclass(slots=True)
class TargetTrack:
    """Tracked target state used to compute an engagement solution."""

    target_id: str
    distance_m: float
    bearing_deg: float
    elevation_deg: float
    velocity_mps: float = 0.0
    heading_deg: float = 0.0
    confidence: float = 1.0
    ir_signature: float = 0.0
    updated_at: datetime = field(default_factory=_utc_now)

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000.0


@dataclass(slots=True, frozen=True)
class AimSolution:
    """Fire-control aim solution returned to the weapon controller."""

    target_id: str
    azimuth_deg: float
    elevation_deg: float
    lead_seconds: float
    confidence: float
    fire_permitted: bool


@dataclass(slots=True, frozen=True)
class EngagementRecord:
    """Immutable audit log entry for lethal or obscurant effects."""

    timestamp: datetime
    payload_name: str
    action: str
    operator_id: str
    target_id: str
    rounds_expended: int
    distance_m: float
    notes: str = ""


class EngagementError(RuntimeError):
    """Raised when engagement constraints block fire authorization."""


@runtime_checkable
class PayloadAdapter(Protocol):
    """Common contract for supervised payload adapters."""

    payload_name: str
    effective_range_km: float
    ammo_remaining: int

    def track_target(self, track: TargetTrack) -> None:
        """Update/insert a target track used for fire-control decisions."""

    def compute_aim_solution(self, target_id: str) -> AimSolution:
        """Build an aim solution for a tracked target."""

    def engage_target(
        self,
        target_id: str,
        *,
        authorization: OperatorAuthorization,
        rounds: int = 1,
        action: str = "engage",
    ) -> EngagementRecord:
        """Execute a supervised engagement action."""

    def apply_cooling(self, seconds: float) -> float:
        """Apply cooling to the payload barrel and return new temperature."""


class BasePayloadAdapter:
    """Base supervised weapon adapter with common fire-control primitives."""

    ambient_temperature_c: float = 25.0

    def __init__(
        self,
        *,
        payload_name: str,
        caliber: str,
        max_ammo: int,
        effective_range_km: float,
        rate_of_fire_rpm: int,
        projectile_velocity_mps: float,
        heat_per_round_c: float,
        cooling_rate_c_per_second: float,
        max_barrel_temp_c: float,
    ) -> None:
        self.payload_name = payload_name
        self.caliber = caliber
        self.max_ammo = max_ammo
        self.ammo_remaining = max_ammo
        self.effective_range_km = effective_range_km
        self.rate_of_fire_rpm = rate_of_fire_rpm
        self.projectile_velocity_mps = projectile_velocity_mps
        self.heat_per_round_c = heat_per_round_c
        self.cooling_rate_c_per_second = cooling_rate_c_per_second
        self.max_barrel_temp_c = max_barrel_temp_c

        self.barrel_temperature_c = self.ambient_temperature_c
        self.target_tracks: dict[str, TargetTrack] = {}
        self.engagement_log: list[EngagementRecord] = []
        self.autonomous_release_enabled = False
        self.total_rounds_fired = 0

    def _require_authorization(
        self,
        *,
        authorization: OperatorAuthorization | None,
        action: str,
    ) -> None:
        if authorization is None:
            raise EngagementError("OperatorAuthorization is required for all engagement actions.")
        if not authorization.allows(action):
            raise EngagementError(f"Authorization does not allow action '{action}' or has expired.")

    def _must_have_track(self, target_id: str) -> TargetTrack:
        track = self.target_tracks.get(target_id)
        if track is None:
            raise EngagementError(f"Target '{target_id}' is not tracked.")
        return track

    def track_target(self, track: TargetTrack) -> None:
        """Store or refresh target track data."""
        if track.distance_m <= 0:
            raise ValueError("distance_m must be positive.")
        if not 0.0 <= track.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1.")
        self.target_tracks[track.target_id] = track

    def compute_aim_solution(self, target_id: str) -> AimSolution:
        """Compute a simple lead solution for target interception."""
        track = self._must_have_track(target_id)
        time_to_target = min(track.distance_m / max(self.projectile_velocity_mps, 1.0), 3.0)
        crossing_angle = radians((track.heading_deg - track.bearing_deg) % 360.0)
        lateral_m = track.velocity_mps * time_to_target * cos(crossing_angle)
        lead_deg = lateral_m / max(track.distance_m, 1.0) * 57.2958
        azimuth = (track.bearing_deg + lead_deg) % 360.0
        max_elevation_delta = 10.0
        elevation = max(min(track.elevation_deg, max_elevation_delta), -max_elevation_delta)
        permitted = (
            track.distance_km <= self.effective_range_km
            and self.ammo_remaining > 0
            and self.barrel_temperature_c < self.max_barrel_temp_c
        )
        return AimSolution(
            target_id=target_id,
            azimuth_deg=azimuth,
            elevation_deg=elevation,
            lead_seconds=time_to_target,
            confidence=track.confidence,
            fire_permitted=permitted,
        )

    def can_engage(self, target_id: str, rounds: int = 1) -> tuple[bool, str]:
        """Validate all tactical safety constraints before release."""
        if rounds <= 0:
            return False, "round count must be positive"
        if rounds > self.ammo_remaining:
            return False, "insufficient ammunition"
        if self.barrel_temperature_c + rounds * self.heat_per_round_c >= self.max_barrel_temp_c:
            return False, "barrel overheat protection active"
        track = self.target_tracks.get(target_id)
        if track is None:
            return False, "target is not tracked"
        if track.distance_km > self.effective_range_km:
            return False, "target outside effective range"
        return True, "ready"

    def engage_target(
        self,
        target_id: str,
        *,
        authorization: OperatorAuthorization,
        rounds: int = 1,
        action: str = "engage",
    ) -> EngagementRecord:
        """Execute a supervised target engagement and write an audit record."""
        self._require_authorization(authorization=authorization, action=action)
        ready, reason = self.can_engage(target_id, rounds)
        if not ready:
            raise EngagementError(reason)

        track = self._must_have_track(target_id)
        _ = self.compute_aim_solution(target_id)
        self.ammo_remaining -= rounds
        self.total_rounds_fired += rounds
        self.barrel_temperature_c += rounds * self.heat_per_round_c

        record = EngagementRecord(
            timestamp=_utc_now(),
            payload_name=self.payload_name,
            action=action,
            operator_id=authorization.operator_id,
            target_id=target_id,
            rounds_expended=rounds,
            distance_m=track.distance_m,
        )
        self.engagement_log.append(record)
        return record

    def apply_cooling(self, seconds: float) -> float:
        """Cool barrel temperature; used for sustained-fire discipline."""
        if seconds < 0:
            raise ValueError("seconds must be non-negative.")
        self.barrel_temperature_c = max(
            self.ambient_temperature_c,
            self.barrel_temperature_c - (seconds * self.cooling_rate_c_per_second),
        )
        return self.barrel_temperature_c

    def reload(self, rounds: int) -> int:
        """Top up available ammunition from support logistics."""
        if rounds <= 0:
            raise ValueError("rounds must be positive.")
        self.ammo_remaining = min(self.max_ammo, self.ammo_remaining + rounds)
        return self.ammo_remaining

    def attempt_autonomous_release(self, target_id: str) -> None:
        """Hard-stop autonomous fire paths in tactical supervision mode."""
        raise EngagementError(
            f"Autonomous fire-release is disabled for {self.payload_name}; "
            "operator authorization is mandatory."
        )


class RCWS127Adapter(BasePayloadAdapter):
    """Remote 12.7 mm station (.50 BMG), supervised direct-fire adapter."""

    def __init__(self) -> None:
        super().__init__(
            payload_name="RCWS127",
            caliber="12.7mm (.50 BMG)",
            max_ammo=400,
            effective_range_km=2.5,
            rate_of_fire_rpm=650,
            projectile_velocity_mps=890.0,
            heat_per_round_c=0.38,
            cooling_rate_c_per_second=1.25,
            max_barrel_temp_c=220.0,
        )


class RCWS145Adapter(BasePayloadAdapter):
    """Remote 14.5 mm station for heavier anti-material effects."""

    def __init__(self) -> None:
        super().__init__(
            payload_name="RCWS145",
            caliber="14.5mm",
            max_ammo=300,
            effective_range_km=3.5,
            rate_of_fire_rpm=600,
            projectile_velocity_mps=980.0,
            heat_per_round_c=0.45,
            cooling_rate_c_per_second=1.35,
            max_barrel_temp_c=225.0,
        )


class SICHAdapter(BasePayloadAdapter):
    """SICH combat module: 30 mm main gun + PKT coax + smoke launcher."""

    module_weight_kg: int = 1600

    def __init__(self) -> None:
        super().__init__(
            payload_name="SICH",
            caliber="30mm ZTM-1",
            max_ammo=290,
            effective_range_km=4.0,
            rate_of_fire_rpm=330,
            projectile_velocity_mps=970.0,
            heat_per_round_c=0.58,
            cooling_rate_c_per_second=1.6,
            max_barrel_temp_c=260.0,
        )
        self.pkt_762_ammo = 2000
        self.smoke_charges = 6

    def engage_main_cannon(
        self,
        target_id: str,
        *,
        authorization: OperatorAuthorization,
        rounds: int = 1,
    ) -> EngagementRecord:
        return self.engage_target(
            target_id,
            authorization=authorization,
            rounds=rounds,
            action="engage_main_cannon",
        )

    def engage_coaxial(
        self,
        target_id: str,
        *,
        authorization: OperatorAuthorization,
        rounds: int = 10,
    ) -> EngagementRecord:
        self._require_authorization(authorization=authorization, action="engage_coaxial")
        track = self._must_have_track(target_id)
        if rounds <= 0:
            raise EngagementError("round count must be positive")
        if rounds > self.pkt_762_ammo:
            raise EngagementError("insufficient 7.62mm coaxial ammunition")
        if track.distance_km > 1.5:
            raise EngagementError("coaxial target outside effective range")
        self.pkt_762_ammo -= rounds
        record = EngagementRecord(
            timestamp=_utc_now(),
            payload_name=self.payload_name,
            action="engage_coaxial",
            operator_id=authorization.operator_id,
            target_id=target_id,
            rounds_expended=rounds,
            distance_m=track.distance_m,
            notes="7.62mm PKT coaxial engagement",
        )
        self.engagement_log.append(record)
        return record

    def deploy_smoke(
        self,
        *,
        authorization: OperatorAuthorization,
        salvos: int = 1,
    ) -> EngagementRecord:
        # Smoke release can mask maneuver under contact; still requires human release authority.
        self._require_authorization(authorization=authorization, action="deploy_smoke")
        if salvos <= 0:
            raise EngagementError("salvos must be positive")
        if salvos > self.smoke_charges:
            raise EngagementError("insufficient smoke charges")
        self.smoke_charges -= salvos
        record = EngagementRecord(
            timestamp=_utc_now(),
            payload_name=self.payload_name,
            action="deploy_smoke",
            operator_id=authorization.operator_id,
            target_id="self-screen",
            rounds_expended=salvos,
            distance_m=0.0,
            notes="Smoke obscuration deployed",
        )
        self.engagement_log.append(record)
        return record


class OrionZU23Adapter(BasePayloadAdapter):
    """Twin 23 mm anti-air adapter with queued engagement workflow."""

    def __init__(self) -> None:
        super().__init__(
            payload_name="OrionZU23",
            caliber="Twin 23mm",
            max_ammo=100,
            effective_range_km=2.5,
            rate_of_fire_rpm=1800,
            projectile_velocity_mps=970.0,
            heat_per_round_c=0.32,
            cooling_rate_c_per_second=1.8,
            max_barrel_temp_c=255.0,
        )
        self.target_queue: Deque[str] = deque()

    def queue_target(self, target_id: str) -> None:
        self._must_have_track(target_id)
        if target_id not in self.target_queue:
            self.target_queue.append(target_id)

    def clear_queue(self) -> None:
        self.target_queue.clear()

    def engage_next_target(
        self,
        *,
        authorization: OperatorAuthorization,
        burst_seconds: float = 0.5,
    ) -> EngagementRecord:
        self._require_authorization(authorization=authorization, action="engage_queue")
        if not self.target_queue:
            raise EngagementError("target queue is empty")
        if burst_seconds <= 0:
            raise EngagementError("burst_seconds must be positive")
        target_id = self.target_queue[0]
        rounds = max(1, int(self.rate_of_fire_rpm * (burst_seconds / 60.0)))
        record = self.engage_target(
            target_id,
            authorization=authorization,
            rounds=rounds,
            action="engage_queue",
        )
        self.target_queue.popleft()
        return record


class MANPADSAdapter(BasePayloadAdapter):
    """IR-guided SHORAD launcher with supervised missile release."""

    def __init__(self) -> None:
        super().__init__(
            payload_name="MANPADS",
            caliber="Missile",
            max_ammo=2,
            effective_range_km=6.5,
            rate_of_fire_rpm=2,
            projectile_velocity_mps=650.0,
            heat_per_round_c=4.0,
            cooling_rate_c_per_second=2.5,
            max_barrel_temp_c=120.0,
        )
        self.guidance_mode = "IR-guided"
        self.minimum_lock_quality = 0.55
        self._lock_quality: dict[str, float] = {}

    def update_ir_lock(self, target_id: str, lock_quality: float) -> None:
        if not 0.0 <= lock_quality <= 1.0:
            raise ValueError("lock_quality must be between 0 and 1.")
        self._must_have_track(target_id)
        self._lock_quality[target_id] = lock_quality

    def launch_missile(
        self,
        target_id: str,
        *,
        authorization: OperatorAuthorization,
    ) -> EngagementRecord:
        self._require_authorization(authorization=authorization, action="launch_missile")
        lock_quality = self._lock_quality.get(target_id, 0.0)
        if lock_quality < self.minimum_lock_quality:
            raise EngagementError("IR lock quality is below launch threshold")
        return self.engage_target(
            target_id,
            authorization=authorization,
            rounds=1,
            action="launch_missile",
        )


__all__ = [
    "AimSolution",
    "BasePayloadAdapter",
    "EngagementError",
    "EngagementRecord",
    "MANPADSAdapter",
    "OperatorAuthorization",
    "OrionZU23Adapter",
    "PayloadAdapter",
    "RCWS127Adapter",
    "RCWS145Adapter",
    "SICHAdapter",
    "TargetTrack",
]
