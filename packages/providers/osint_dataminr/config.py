"""Configuration for Dataminr provider adapter."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DataminrConfig:
    base_url: str = "https://gateway.dataminr.com"
    token_url: str = "https://gateway.dataminr.com/oauth/token"
    rate_limit_rpm: int = 60
    alert_types: list[str] = field(default_factory=lambda: ["alert", "urgentAlert", "flash"])
    s3m_watchlists: list[str] = field(default_factory=lambda: ["saudi_security", "gulf_maritime", "mena_military", "cyber_gcc", "red_sea_incidents"])
