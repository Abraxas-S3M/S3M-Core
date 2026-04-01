"""Abstract base class that every S3M provider adapter must implement."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type


class ProviderCategory(Enum):
    """Categories matching the 90-API PDF classification."""
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


class ProviderTier(Enum):
    """Pricing tier — affects scheduling and fallback behavior."""
    FREE = "free"
    FREEMIUM = "freemium"
    PREMIUM = "premium"
    GOVERNMENT = "government"
    OPEN_STANDARD = "open_standard"


class OperatingMode(Enum):
    """Dual-mode: online for ingestion, airgapped for field deployment."""
    ONLINE = "online"          # Can call external APIs
    AIRGAPPED = "airgapped"    # Read from local cache ONLY — no network egress


class ProviderHealth(Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILING = "failing"
    OFFLINE = "offline"
    DISABLED = "disabled"


@dataclass
class ProviderManifest:
    """Declares what a provider offers — registered in the ProviderRegistry."""
    provider_id: str                          # e.g., "geoint-copernicus"
    name: str                                 # e.g., "Copernicus Open Access Hub"
    category: ProviderCategory
    tier: ProviderTier
    base_url: str                             # e.g., "https://scihub.copernicus.eu/dhus"
    auth_type: str                            # "api_key", "oauth2", "certificate", "none"
    rate_limit_rpm: int                       # requests per minute
    supported_schemas: List[str]              # normalized schema names this provider outputs
    required_env_vars: List[str]              # env vars needed for credentials
    description: str
    docs_url: str                             # official API documentation URL
    airgap_capable: bool = True               # can operate from cached data
    enabled: bool = True                      # feature flag
    tags: List[str] = field(default_factory=list)


class ProviderAdapter(ABC):
    """
    Abstract base class for all S3M provider adapters.
    
    Every adapter must implement:
    - get_manifest(): declares capabilities and requirements
    - validate_credentials(): checks auth before first call
    - fetch(): retrieves raw data from the provider (online) or local cache (airgapped)
    - normalize(): converts raw data to S3M normalized schemas
    - health_check(): reports provider health
    
    The framework handles: retries, rate limiting, circuit breaking, caching,
    audit logging, and mode switching (online/airgapped).
    """

    def __init__(self, mode: OperatingMode = OperatingMode.ONLINE):
        self.mode = mode
        self._manifest: Optional[ProviderManifest] = None
        self._last_health: ProviderHealth = ProviderHealth.OFFLINE
        self._last_fetch_at: Optional[datetime] = None
        self._fetch_count: int = 0
        self._error_count: int = 0

    @abstractmethod
    def get_manifest(self) -> ProviderManifest:
        """Return the provider's capability manifest."""
        ...

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Validate that required credentials are available and valid.
        Returns True if credentials are valid, False otherwise.
        In airgapped mode, may return True if local data exists."""
        ...

    @abstractmethod
    def fetch(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Fetch raw data from the provider.
        In ONLINE mode: calls the external API.
        In AIRGAPPED mode: reads from local cache/data store.
        Returns raw provider response as dict."""
        ...

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> List[Any]:
        """Convert raw provider data to S3M normalized schema objects.
        Returns list of normalized records (NormalizedGeoObservation, NormalizedThreatIndicator, etc.)"""
        ...

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Check provider health. Returns dict with:
        - status: ProviderHealth
        - latency_ms: Optional[float]
        - last_successful_fetch: Optional[datetime]
        - error_count: int
        - detail: str
        """
        ...

    # --- Concrete methods provided by the framework ---

    def fetch_and_normalize(self, params: Dict[str, Any] = None) -> List[Any]:
        """Convenience: fetch + normalize in one call."""
        raw = self.fetch(params)
        return self.normalize(raw)

    def get_mode(self) -> OperatingMode:
        return self.mode

    def set_mode(self, mode: OperatingMode):
        self.mode = mode

    def is_airgapped(self) -> bool:
        return self.mode == OperatingMode.AIRGAPPED

    def get_stats(self) -> Dict[str, Any]:
        return {
            "provider_id": self.get_manifest().provider_id,
            "mode": self.mode.value,
            "health": self._last_health.value,
            "fetch_count": self._fetch_count,
            "error_count": self._error_count,
            "last_fetch_at": self._last_fetch_at.isoformat() if self._last_fetch_at else None,
        }
