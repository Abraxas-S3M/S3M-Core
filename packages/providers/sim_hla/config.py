"""Configuration for the simulation-only HLA interoperability adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


HLA_OBJECT_CLASSES: dict[str, dict[str, list[str]]] = {
    "Aircraft": {
        "attributes": ["Position", "Orientation", "Velocity", "ForceIdentifier", "Marking", "DamageState"]
    },
    "GroundVehicle": {
        "attributes": ["Position", "Orientation", "Velocity", "ForceIdentifier", "Marking", "DamageState"]
    },
    "SurfaceVessel": {
        "attributes": ["Position", "Orientation", "Velocity", "ForceIdentifier", "Marking", "DamageState"]
    },
    "Munition": {"attributes": ["Position", "Velocity", "LauncherID", "TargetID", "MunitionType"]},
    "Sensor": {"attributes": ["Position", "SensorType", "Range", "Status"]},
}


HLA_INTERACTIONS: dict[str, dict[str, list[str]]] = {
    "WeaponFire": {
        "parameters": [
            "FiringObjectIdentifier",
            "TargetObjectIdentifier",
            "MunitionType",
            "FiringLocation",
        ]
    },
    "Detonation": {
        "parameters": [
            "FiringObjectIdentifier",
            "TargetObjectIdentifier",
            "DetonationLocation",
            "Result",
        ]
    },
    "RadioTransmit": {"parameters": ["TransmitterID", "Frequency", "Data"]},
}


@dataclass(slots=True)
class HLAConfig:
    rti_type: str = field(default_factory=lambda: os.getenv("S3M_HLA_RTI_TYPE", "certi"))
    certi_host: str = field(default_factory=lambda: os.getenv("S3M_HLA_RTI_HOST", "localhost"))
    certi_port: int = field(default_factory=lambda: int(os.getenv("S3M_HLA_RTI_PORT", "11000")))
    rate_limit_rpm: int = 120
    default_federation_name: str = "S3M_Federation"
    default_federate_name: str = "S3M_Federate"
    fom_path: str = "configs/interop/s3m_fom.xml"
    rpr_fom_version: str = "2.0"
    time_management: str = "time_stepped"
    time_step_seconds: float = 0.1
    object_classes: dict[str, Any] = field(default_factory=lambda: dict(HLA_OBJECT_CLASSES))
    interaction_classes: dict[str, Any] = field(default_factory=lambda: dict(HLA_INTERACTIONS))
