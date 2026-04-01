"""Configuration for ACLED conflict event integration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ACLEDConfig:
    base_url: str = "https://api.acleddata.com/acled/read"
    rate_limit_rpm: int = 5
    daily_quota: int = 500
    saudi_relevant_countries: list[str] = field(
        default_factory=lambda: [
            "Saudi Arabia",
            "Yemen",
            "Oman",
            "United Arab Emirates",
            "Kuwait",
            "Bahrain",
            "Qatar",
            "Iraq",
            "Iran",
            "Syria",
            "Jordan",
            "Egypt",
            "Sudan",
            "Eritrea",
            "Djibouti",
            "Somalia",
        ]
    )
    conflict_event_types: list[str] = field(
        default_factory=lambda: [
            "Battles",
            "Explosions/Remote violence",
            "Violence against civilians",
        ]
    )
    all_event_types: list[str] = field(
        default_factory=lambda: [
            "Battles",
            "Explosions/Remote violence",
            "Violence against civilians",
            "Protests",
            "Riots",
            "Strategic developments",
        ]
    )
    interaction_codes: dict[int, str] = field(
        default_factory=lambda: {
            10: "state forces vs civilians",
            12: "state forces vs rebels",
            17: "state forces vs external/other forces",
            20: "rebel groups vs civilians",
            28: "rioters vs police",
            30: "protesters vs state forces",
            47: "explosive attacks on civilians",
            60: "strategic non-violent developments",
        }
    )
