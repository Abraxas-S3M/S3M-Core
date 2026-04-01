"""Provider registry and fetch-job operational models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from integration_sdk.base.provider_adapter import ProviderHealth


@dataclass
class ProviderAccount:
    account_id: str
    provider_id: str
    active: bool = True
    tier: str = "free"


@dataclass
class FetchJob:
    job_id: str
    provider_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    record_count: int = 0


@dataclass
class HealthStatus:
    provider_id: str
    status: ProviderHealth
    latency_ms: Optional[float] = None
    detail: str = ""
