"""S3M platform adapter — weapon payload systems."""

from .weapon_adapters import (
    AimSolution,
    BasePayloadAdapter,
    EngagementError,
    EngagementRecord,
    MANPADSAdapter,
    OperatorAuthorization,
    OrionZU23Adapter,
    PayloadAdapter,
    RCWS127Adapter,
    RCWS145Adapter,
    SICHAdapter,
    TargetTrack,
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
