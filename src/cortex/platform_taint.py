"""Taint labelling for log aggregation and IR platform text payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, MutableMapping, Optional

from src.cortex.provenance import EventProvenance
from src.cortex.taint import Trust, injection_signal, quarantine_extract

TEXT_FIELD_SUFFIX = "_trust"
LABELED_SUFFIX = "_labeled"

_PLATFORM_FREE_TEXT_KEYS = {
    "graylog": ("short_message", "full_message", "_message", "message"),
    "opensearch": ("message", "description", "title", "content"),
    "thehive": ("title", "description", "summary"),
    "misp": ("comment", "info", "value"),
    "cortex": ("analysis", "summary", "report"),
    "dfir_iris": ("description", "title", "content", "note"),
}

_PLATFORM_TYPED_KEYS = {
    "src_ip": "ip",
    "dest_ip": "ip",
    "ip-src": "ip",
    "ip-dst": "ip",
    "source_ip": "ip",
}


def _ensure_provenance(
    record: MutableMapping[str, Any],
    *,
    source_system: str,
    sensor_id: str,
) -> EventProvenance:
    existing = record.get("provenance")
    if isinstance(existing, EventProvenance):
        return existing
    if isinstance(existing, dict):
        provenance = EventProvenance.from_dict(existing)
    else:
        provenance = EventProvenance(
            source_system=source_system,
            sensor_id=sensor_id,
            ingest_time=datetime.now(timezone.utc),
        )
    record["provenance"] = provenance
    return provenance


def label_platform_record(
    record: MutableMapping[str, Any],
    *,
    source_system: str,
    sensor_id: str = "platform-ingest",
    extra_free_text: Optional[List[str]] = None,
) -> MutableMapping[str, Any]:
    """Annotate a dict returned from IR or log systems with trust metadata."""
    provenance = _ensure_provenance(record, source_system=source_system, sensor_id=sensor_id)
    keys = list(_PLATFORM_FREE_TEXT_KEYS.get(source_system, ()))
    if extra_free_text:
        keys.extend(extra_free_text)

    tags = record.get("tags")
    if not isinstance(tags, list):
        tags = []
    injection_hit = False

    for key in keys:
        if key not in record:
            continue
        value = record.get(key)
        if value is None:
            continue
        text = str(value)
        provenance.field_trust[key] = Trust.UNTRUSTED
        record[f"{key}{TEXT_FIELD_SUFFIX}"] = Trust.UNTRUSTED.value
        if injection_signal(text):
            injection_hit = True

    for key, kind in _PLATFORM_TYPED_KEYS.items():
        if key not in record:
            continue
        labeled = quarantine_extract(record.get(key), kind, source=key, trust=Trust.UNTRUSTED)
        provenance.field_trust[key] = labeled.trust
        record[f"{key}{LABELED_SUFFIX}"] = {
            "value": labeled.value,
            "trust": labeled.trust.value,
            "raw": labeled.raw,
        }

    if injection_hit and "possible_prompt_injection" not in tags:
        tags.append("possible_prompt_injection")
    record["tags"] = tags
    record["provenance"] = provenance.to_dict()
    return record


def label_platform_records(
    records: List[MutableMapping[str, Any]],
    *,
    source_system: str,
    sensor_id: str = "platform-ingest",
) -> List[MutableMapping[str, Any]]:
    return [label_platform_record(dict(item), source_system=source_system, sensor_id=sensor_id) for item in records]
