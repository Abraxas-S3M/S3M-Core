"""Provenance and taint application for Layer 02 ThreatEvent objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.cortex.provenance import EventProvenance
from src.cortex.taint import AssetInventory, Labeled, Trust, endorse, injection_signal, quarantine_extract
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource

SOCAlertCallback = Optional[Callable[[ThreatEvent], None]]

_pending_injection_alerts: List[ThreatEvent] = []


def drain_injection_soc_alerts() -> List[ThreatEvent]:
    """Return and clear low-severity SOC alerts raised during injection scans."""
    alerts = list(_pending_injection_alerts)
    _pending_injection_alerts.clear()
    return alerts


def _field_trust(event: ThreatEvent, field: str, default: Trust = Trust.UNTRUSTED) -> Trust:
    if event.provenance and field in event.provenance.field_trust:
        return event.provenance.field_trust[field]
    return default


def _labeled_from_raw(event: ThreatEvent, field: str, kind: str, raw_key: str) -> Labeled[Any]:
    trust = _field_trust(event, field)
    raw_value = event.raw_data.get(raw_key)
    return quarantine_extract(raw_value, kind, source=field, trust=trust)


def _set_endorsed_field(event: ThreatEvent, field: str, labeled: Labeled[Any]) -> None:
    event._endorsed_fields[field] = labeled
    if event.provenance is not None and labeled.value is not None:
        event.provenance.field_trust[field] = labeled.trust


def labeled_src_ip(event: ThreatEvent) -> Labeled[str]:
    if "src_ip" in event._endorsed_fields:
        return event._endorsed_fields["src_ip"]
    labeled = _labeled_from_raw(event, "src_ip", "ip", "src_ip")
    if labeled.value is None and "source_ip" in event.raw_data:
        labeled = _labeled_from_raw(event, "src_ip", "ip", "source_ip")
    return labeled


def labeled_dst_ip(event: ThreatEvent) -> Labeled[str]:
    if "dst_ip" in event._endorsed_fields:
        return event._endorsed_fields["dst_ip"]
    return _labeled_from_raw(event, "dst_ip", "ip", "dest_ip")


def labeled_src_port(event: ThreatEvent) -> Labeled[int]:
    if "src_port" in event._endorsed_fields:
        return event._endorsed_fields["src_port"]
    return _labeled_from_raw(event, "src_port", "port", "src_port")


def labeled_dst_port(event: ThreatEvent) -> Labeled[int]:
    if "dst_port" in event._endorsed_fields:
        return event._endorsed_fields["dst_port"]
    return _labeled_from_raw(event, "dst_port", "port", "dest_port")


def labeled_hostname(event: ThreatEvent) -> Labeled[str]:
    if "hostname" in event._endorsed_fields:
        return event._endorsed_fields["hostname"]
    for key in ("hostname", "host", "agent_name"):
        if key in event.raw_data:
            labeled = _labeled_from_raw(event, "hostname", "hostname", key)
            if labeled.value is not None:
                return labeled
    return _labeled_from_raw(event, "hostname", "hostname", "hostname")


def labeled_hash_sha256(event: ThreatEvent) -> Labeled[str]:
    return _labeled_from_raw(event, "hash_sha256", "sha256", "sha256")


def labeled_cve_id(event: ThreatEvent) -> Labeled[str]:
    return _labeled_from_raw(event, "cve_id", "cve", "cve_id")


def attach_threat_accessors() -> None:
    """Bind typed Labeled accessors onto ThreatEvent (idempotent)."""

    if getattr(ThreatEvent, "_taint_accessors_attached", False):
        return

    ThreatEvent.labeled_src_ip = lambda self: labeled_src_ip(self)
    ThreatEvent.labeled_dst_ip = lambda self: labeled_dst_ip(self)
    ThreatEvent.labeled_src_port = lambda self: labeled_src_port(self)
    ThreatEvent.labeled_dst_port = lambda self: labeled_dst_port(self)
    ThreatEvent.labeled_hostname = lambda self: labeled_hostname(self)
    ThreatEvent.labeled_hash_sha256 = lambda self: labeled_hash_sha256(self)
    ThreatEvent.labeled_cve_id = lambda self: labeled_cve_id(self)
    ThreatEvent._set_endorsed_field = _set_endorsed_field
    ThreatEvent._taint_accessors_attached = True


def _raise_injection_soc_alert(parent: ThreatEvent, field: str, excerpt: str, callback: SOCAlertCallback) -> None:
    alert = ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.LOW,
        category=ThreatCategory.CYBER,
        title="Possible prompt injection in ingested evidence",
        description=f"Injection-like pattern in {field} for event {parent.event_id}.",
        raw_data={
            "parent_event_id": parent.event_id,
            "field": field,
            "excerpt": excerpt[:512],
            "source_system": parent.provenance.source_system if parent.provenance else "unknown",
        },
        confidence=0.55,
        classification=parent.classification,
        tags=["soc_signal", "possible_prompt_injection"],
    )
    if parent.provenance:
        alert.provenance = EventProvenance(
            source_system=parent.provenance.source_system,
            sensor_id=parent.provenance.sensor_id,
            ingest_time=parent.provenance.ingest_time,
            field_trust={"excerpt": Trust.UNTRUSTED},
        )
    _pending_injection_alerts.append(alert)
    if callback is not None:
        callback(alert)


def apply_threat_event_taint(
    event: ThreatEvent,
    *,
    source_system: str,
    sensor_id: str,
    observed_fields: Iterable[str],
    untrusted_fields: Iterable[str],
    free_text_blobs: Optional[Dict[str, str]] = None,
    soc_alert_callback: SOCAlertCallback = None,
) -> ThreatEvent:
    """Label field trust, scan free text for injection, and preserve all evidence."""
    ingest_time = datetime.now(timezone.utc)
    field_trust: Dict[str, Trust] = {}
    for name in observed_fields:
        field_trust[str(name)] = Trust.OBSERVED
    for name in untrusted_fields:
        field_trust[str(name)] = Trust.UNTRUSTED

    event.provenance = EventProvenance(
        source_system=source_system,
        sensor_id=sensor_id,
        ingest_time=ingest_time,
        field_trust=field_trust,
    )
    event._endorsed_fields = {}

    injection_hit = False
    blobs = dict(free_text_blobs or {})
    blobs.setdefault("title", event.title)
    blobs.setdefault("description", event.description)
    for field_name, text in blobs.items():
        if injection_signal(text):
            injection_hit = True
            _raise_injection_soc_alert(event, field_name, str(text), soc_alert_callback)

    if injection_hit:
        if "possible_prompt_injection" not in event.tags:
            event.tags.append("possible_prompt_injection")
        # Tactical hardening: poisoned free-text downgrades every field to UNTRUSTED for automation.
        for key in list(event.provenance.field_trust.keys()):
            event.provenance.field_trust[key] = Trust.UNTRUSTED

    return event


def endorse_threat_event_inventory(event: ThreatEvent, inventory: AssetInventory) -> ThreatEvent:
    """Public wrapper used by adapters and tests."""
    inv_map = {
        "ips": inventory["ips"] if "ips" in inventory else set(),
        "ports": inventory["ports"] if "ports" in inventory else set(),
        "hostnames": inventory["hostnames"] if "hostnames" in inventory else set(),
        "asset_ids": inventory["asset_ids"] if "asset_ids" in inventory else set(),
    }
    inv = AssetInventory(**inv_map)
    accessors: List[Tuple[str, str, Labeled[Any]]] = [
        ("src_ip", "ips", event.labeled_src_ip()),
        ("dst_ip", "ips", event.labeled_dst_ip()),
        ("src_port", "ports", event.labeled_src_port()),
        ("dst_port", "ports", event.labeled_dst_port()),
        ("hostname", "hostnames", event.labeled_hostname()),
    ]
    for field_name, bucket, labeled in accessors:
        endorsed = endorse(labeled, verified=inv.contains(bucket, labeled.value))
        event._set_endorsed_field(field_name, endorsed)
    for aid in event.asset_ids:
        if inv.contains("asset_ids", aid):
            if event.provenance:
                event.provenance.field_trust[f"asset_id:{aid}"] = Trust.VERIFIED
    return event


attach_threat_accessors()
