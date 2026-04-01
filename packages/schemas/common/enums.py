"""Common enumerations used by normalized provider schemas."""

from __future__ import annotations

from enum import Enum


class ProviderCategory(Enum):
    GEOINT = "geoint"
    CYBER_THREAT_INTEL = "cyber_threat_intel"
    OSINT_GLOBAL_EVENTS = "osint_global_events"
    MARITIME = "maritime"
    AIRSPACE_FLIGHT = "airspace_flight"
    WEATHER_ENVIRONMENT = "weather_environment"
    MAPPING_TERRAIN = "mapping_terrain"
    DRONE_UAS = "drone_uas"
    C4I_INTEROP = "c4i_interop"
    SOVEREIGN_REGIONAL = "sovereign_regional"
    INVESTIGATION = "investigation"
    AI_ML_SERVICES = "ai_ml_services"


class DataClassification(Enum):
    UNCLASSIFIED = "unclassified"
    FOUO = "fouo"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


class ConfidenceLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
