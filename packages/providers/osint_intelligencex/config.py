"""Configuration for Intelligence X OSINT provider."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IntelligenceXConfig:
    base_url: str = "https://2.intelx.io"
    rate_limit_rpm: int = 3
    hourly_quota: int = 3
    max_results_per_search: int = 100
    poll_interval_seconds: int = 2
    max_poll_attempts: int = 30
    bucket_names: dict[int, str] = field(
        default_factory=lambda: {
            0: "all",
            1: "pastes",
            2: "darknet",
            3: "whois_domain",
            4: "whois_ip",
            5: "news",
            6: "web",
            7: "usenet",
            12: "dumpster",
        }
    )
    media_types: dict[int, str] = field(
        default_factory=lambda: {
            0: "all",
            1: "paste",
            2: "darknet_market",
            3: "whois_domain",
            5: "news",
            24: "document",
        }
    )
    saudi_search_terms: list[str] = field(
        default_factory=lambda: [
            "aramco.com",
            "saudi.gov.sa",
            "ntc.sa",
            "sdaia.gov.sa",
            "moda.gov.sa",
            "stc.com.sa",
            "sabic.com",
        ]
    )
