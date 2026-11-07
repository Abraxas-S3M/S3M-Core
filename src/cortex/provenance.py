"""Event provenance metadata shared across threat and platform adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from src.cortex.taint import Trust


@dataclass
class EventProvenance:
    """Where an event entered the stack and how much each field may be trusted."""

    source_system: str
    sensor_id: str
    ingest_time: datetime
    field_trust: Dict[str, Trust] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_system": self.source_system,
            "sensor_id": self.sensor_id,
            "ingest_time": self.ingest_time.isoformat(),
            "field_trust": {key: trust.value for key, trust in self.field_trust.items()},
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EventProvenance":
        ingest_raw = payload.get("ingest_time")
        ingest_time = datetime.now(timezone.utc)
        if isinstance(ingest_raw, str) and ingest_raw.strip():
            try:
                ingest_time = datetime.fromisoformat(ingest_raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        field_trust_raw = payload.get("field_trust") or {}
        field_trust = {
            str(key): Trust(str(value))
            for key, value in field_trust_raw.items()
            if str(value) in Trust._value2member_map_
        }
        return cls(
            source_system=str(payload.get("source_system", "unknown")),
            sensor_id=str(payload.get("sensor_id", "unknown")),
            ingest_time=ingest_time,
            field_trust=field_trust,
        )
