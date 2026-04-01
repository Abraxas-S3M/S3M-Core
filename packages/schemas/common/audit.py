"""Audit event schema for integration actions and accountability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass
class AuditEvent:
    event_id: str
    provider_id: str
    action: str
    actor: str
    status: str
    detail: str
    classification: str = "UNCLASSIFIED"
    metadata: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None
