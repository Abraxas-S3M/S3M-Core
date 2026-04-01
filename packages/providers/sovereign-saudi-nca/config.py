"""Configuration for Saudi NCA sovereign cyber authority adapter."""

from dataclasses import dataclass, field


@dataclass
class SaudiNCAConfig:
    api_url: str = "https://api.nca.gov.sa/v1"
    rate_limit_rpm: int = 10
    incoming_dir: str = "data/integrations/sovereign-saudi-nca/incoming/"
    advisory_severity_map: dict[str, str] = field(
        default_factory=lambda: {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }
    )
    compliance_frameworks: list[str] = field(default_factory=lambda: ["ECC", "CSCC", "CCC", "OTCC"])
    nca_ioc_types: list[str] = field(default_factory=lambda: ["ip", "domain", "hash", "url", "cve"])
    saudi_critical_sectors: list[str] = field(
        default_factory=lambda: [
            "energy",
            "water",
            "telecommunications",
            "government",
            "finance",
            "healthcare",
            "defense",
            "transportation",
        ]
    )
