"""Configuration for Elm sovereign services adapter."""

from dataclasses import dataclass, field


@dataclass
class ElmConfig:
    api_url: str = "https://api.elm.sa/v1"
    rate_limit_rpm: int = 10
    service_types: list[str] = field(default_factory=lambda: ["identity_verification", "vehicle_registration", "government_records"])
    data_classification: str = "SAUDI_GOVERNMENT_CONFIDENTIAL"
