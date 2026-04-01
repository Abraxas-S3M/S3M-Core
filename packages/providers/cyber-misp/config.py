"""MISP provider configuration."""

from dataclasses import dataclass, field


@dataclass
class MISPConfig:
    base_url: str = "http://localhost:8443"
    verify_ssl: bool = False
    rate_limit_rpm: int = 60
    default_last_days: int = 7
    default_limit: int = 500
    enforce_warninglist: bool = True
    relevant_attribute_types: list[str] = field(
        default_factory=lambda: [
            "ip-src", "ip-dst", "domain", "hostname", "url",
            "md5", "sha1", "sha256", "email-src", "vulnerability",
        ]
    )
    threat_level_map: dict[int, str] = field(default_factory=lambda: {1: "high", 2: "medium", 3: "low", 4: "info"})
