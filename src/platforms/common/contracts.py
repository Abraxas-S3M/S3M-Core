"""Platform adapter protocol contracts for S3M-Core HOOL autonomy.

Uses typing.Protocol for structural subtyping - zero external dependencies.

UNCLASSIFIED - CLOSED-RANGE TRAINING USE ONLY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

from .messages import (
    AimSolution,
    FaultEvent,
    HealthState,
    MobilityCommand,
    OperatorAuthorization,
    PayloadState,
    PlatformState,
    PlatformType,
    SensorCommand,
    Track,
)


@dataclass
class PlatformCapabilities:
    """Describes what a platform can and cannot do."""

    platform_type: PlatformType
    platform_model: str = ""
    has_mobility: bool = False
    has_weapon_payload: bool = False
    has_isr_payload: bool = False
    max_speed_mps: float = 0.0
    sensor_types: List[str] = field(default_factory=list)
    comms_types: List[str] = field(default_factory=list)
    autonomy_levels_supported: List[int] = field(default_factory=lambda: [0, 1])
    operating_temp_range_c: tuple = (-30.0, 55.0)
    environmental_rating: str = "desert_optimized"


@runtime_checkable
class PlatformAdapter(Protocol):
    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def heartbeat(self) -> HealthState: ...
    def read_state(self) -> PlatformState: ...
    def apply_mobility_command(self, cmd: MobilityCommand) -> bool: ...
    def apply_sensor_command(self, cmd: SensorCommand) -> bool: ...
    def safe_state(self) -> bool: ...
    def inject_simulated_telemetry(self, state: PlatformState) -> None: ...
    def report_fault(self, fault: FaultEvent) -> None: ...
    def get_capabilities(self) -> PlatformCapabilities: ...


@runtime_checkable
class PayloadAdapter(Protocol):
    def connect(self) -> bool: ...
    def read_state(self) -> PayloadState: ...
    def track_target(self, track: Track) -> bool: ...
    def hold_on_target(self) -> bool: ...
    def recommend_aim_solution(self, track: Track) -> AimSolution: ...
    def safe_state(self) -> bool: ...
    def operator_authorized_action(self, auth: OperatorAuthorization) -> bool: ...
