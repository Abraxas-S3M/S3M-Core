"""Configuration for the GDELT OSINT global events provider."""

from __future__ import annotations

from dataclasses import dataclass, field


SAUDI_QUERIES = {
    "saudi_military": "saudi military OR saudi defense OR saudi armed forces",
    "yemen_conflict": "yemen war OR houthi OR ansar allah OR bab el mandeb",
    "gulf_security": "persian gulf security OR hormuz OR gcc military",
    "iran_activity": "iran military OR irgc OR iran proxy",
    "red_sea": "red sea attack OR red sea shipping OR red sea security",
    "drone_threat": "drone attack middle east OR uav strike OR loitering munition",
    "cyber_mena": "cyberattack middle east OR cyber iran OR cyber saudi",
    "oil_energy": "saudi oil OR aramco OR opec security",
    "terrorism_mena": "terrorism middle east OR isis OR al qaeda arabian peninsula",
    "diplomacy_gcc": "gcc summit OR saudi diplomacy OR saudi foreign policy",
}


@dataclass(slots=True)
class GDELTConfig:
    doc_api_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    geo_api_url: str = "https://api.gdeltproject.org/api/v2/geo/geo"
    tv_api_url: str = "https://api.gdeltproject.org/api/v2/tv/tv"
    events_csv_base_url: str = "http://data.gdeltproject.org/events"
    rate_limit_rpm: int = 30
    default_timespan: str = "24h"
    saudi_queries: dict[str, str] = field(default_factory=lambda: dict(SAUDI_QUERIES))
    cameo_conflict_prefixes: list[str] = field(default_factory=lambda: ["14", "17", "18", "19", "20"])
    goldstein_severity_map: dict[str, tuple[float, float | None]] = field(
        default_factory=lambda: {
            "critical": (-999.0, -7.0),
            "high": (-7.0, -3.0),
            "medium": (-3.0, 0.0),
            "low": (0.0, None),
        }
    )
    mena_country_codes: list[str] = field(
        default_factory=lambda: ["SA", "YE", "OM", "AE", "KW", "BH", "QA", "IQ", "IR", "SY", "JO", "EG", "SD", "ER", "DJ", "SO"]
    )
