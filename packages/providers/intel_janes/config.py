"""Configuration for Janes premium defense intelligence provider."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class JanesConfig:
    base_url: str = "https://developer.janes.com/api/v1"
    rate_limit_rpm: int = 30
    saudi_equipment_types: list[str] = field(default_factory=lambda: [
        "F-15SA",
        "AH-64E",
        "M1A2",
        "Typhoon",
        "Patriot",
        "THAAD",
        "Al-Riyadh_class_frigate",
    ])
    mena_countries: list[str] = field(default_factory=lambda: ["SA", "AE", "QA", "KW", "BH", "OM", "YE", "IQ", "JO", "EG", "IL"])
