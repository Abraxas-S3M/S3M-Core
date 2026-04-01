"""Identity schemas for provider accounts, credentials, and connector health."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from integration_sdk.base.provider_adapter import ProviderHealth


@dataclass
class ProviderAccount:
    account_id: str
    provider_id: str
    tier: str
    rate_limit_rpm: int
    quota_remaining: int
    quota_resets_at: Optional[datetime]
    active: bool


@dataclass
class CredentialRef:
    provider_id: str
    auth_type: str
    env_var_names: List[str] = field(default_factory=list)
    valid: bool = False
    last_validated: Optional[datetime] = None


@dataclass
class ConnectorHealthStatus:
    provider_id: str
    health: ProviderHealth
    latency_ms: Optional[float]
    last_success: Optional[datetime]
    error_count: int
    circuit_state: str
