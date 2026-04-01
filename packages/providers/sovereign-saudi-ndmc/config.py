"""Configuration for Saudi NDMC sovereign compliance adapter."""

from dataclasses import dataclass, field


DATA_SHARING_AGREEMENT = {
    "authority": "Saudi National Center of Meteorology (NCM)",
    "ministry": "Ministry of Environment, Water and Agriculture",
    "data_types": [
        "weather_observations",
        "forecasts",
        "severe_alerts",
        "aviation_metar",
        "dust_warnings",
    ],
    "classification": "Official Use",
    "retention_days": 365,
    "redistribution": "GCC partners only with approval",
}


@dataclass
class SovereignNDMCConfig:
    government_api_url: str = "https://api.ncm.gov.sa/v1"
    rate_limit_rpm: int = 10
    data_classification: str = "SAUDI_GOVERNMENT_OFFICIAL"
    alert_languages: list[str] = field(default_factory=lambda: ["ar", "en"])
    government_alert_priority: str = "SOVEREIGN_AUTHORITY"
    data_sharing_agreement: dict = field(default_factory=lambda: dict(DATA_SHARING_AGREEMENT))
    sovereign_alert_types: list[str] = field(
        default_factory=lambda: [
            "royal_decree_weather",
            "civil_defense_weather",
            "military_weather_advisory",
            "aviation_weather_warning",
            "maritime_storm_warning",
            "dust_storm_national",
            "extreme_heat_national",
            "flood_warning",
        ]
    )
    chunk5_incoming_dir: str = "data/integrations/weather-saudi-ndmc/incoming/"
