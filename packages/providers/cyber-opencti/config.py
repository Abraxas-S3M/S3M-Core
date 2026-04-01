"""OpenCTI provider configuration."""

from dataclasses import dataclass, field


@dataclass
class OpenCTIConfig:
    base_url: str = "http://localhost:8080"
    graphql_endpoint: str = "/graphql"
    rate_limit_rpm: int = 30
    default_limit: int = 100
    stix_pattern_types: list[str] = field(default_factory=lambda: ["stix", "pcre", "sigma", "snort", "suricata", "yara"])
