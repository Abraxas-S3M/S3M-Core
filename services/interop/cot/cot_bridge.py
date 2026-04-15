"""Bridge S3M force tracks with CoT transport for ATAK interoperability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.interop.cot.cot_event import CotEventFactory
from services.interop.cot.cot_transport import CotTransport


class CotBridge:
    """Translate S3M tracks to CoT and ingest received CoT back into S3M format."""

    def __init__(self, transport: CotTransport, event_factory: CotEventFactory):
        self.transport = transport
        self.event_factory = event_factory
        self._stats = {
            "published": 0,
            "received": 0,
            "crossfed": 0,
            "errors": 0,
            "last_publish_time": None,
        }

    def publish_tracks(self, tracks: list[dict]) -> int:
        """Publish S3M tracks as CoT XML events."""
        if not isinstance(tracks, list):
            raise ValueError("tracks must be a list")

        published = 0
        for track in tracks:
            if not isinstance(track, dict):
                self._stats["errors"] += 1
                continue
            try:
                xml = self.event_factory.build_event(track)
                if self.transport.send(xml):
                    published += 1
                    self._stats["published"] += 1
                    self._stats["last_publish_time"] = datetime.now(timezone.utc).isoformat()
                else:
                    self._stats["errors"] += 1
            except Exception:
                self._stats["errors"] += 1
        return published

    def ingest_received(self) -> list[dict]:
        """Poll received CoT events and return ForceAwareness ingest-track format."""
        rows: list[dict] = []
        while True:
            xml = self.transport.receive()
            if xml is None:
                break
            try:
                parsed = self.event_factory.parse_event(xml)
                mapped_type, _affiliation, _domain = self.event_factory._cot_to_s3m_type(parsed.get("type", "a-u-G"))
                rows.append(
                    {
                        "unit_id": parsed.get("uid"),
                        "position": [
                            float(parsed.get("lat", 0.0)),
                            float(parsed.get("lon", 0.0)),
                            float(parsed.get("hae", 0.0)),
                        ],
                        "role": mapped_type,
                        "status": "active",
                    }
                )
                self._stats["received"] += 1
            except Exception:
                self._stats["errors"] += 1
        return rows

    def start_crossfeed(self, dis_adapter) -> int:
        """Convert DIS entity updates into CoT publication payloads."""
        dis_entities = self._read_dis_entities(dis_adapter)
        if not dis_entities:
            return 0

        converted: list[dict] = []
        for entity in dis_entities:
            if not isinstance(entity, dict):
                continue
            position = entity.get("position", {})
            if isinstance(position, dict):
                lat = float(position.get("lat", position.get("latitude", 0.0)))
                lon = float(position.get("lon", position.get("longitude", 0.0)))
                hae = float(position.get("alt", position.get("altitude", position.get("hae", 0.0))))
            elif isinstance(position, (tuple, list)) and len(position) >= 3:
                lat, lon, hae = float(position[0]), float(position[1]), float(position[2])
            else:
                continue

            force_id = int(entity.get("force_id", 3))
            affiliation = {1: "friendly", 2: "hostile", 3: "neutral"}.get(force_id, "unknown")
            domain = self._domain_from_entity(entity)
            converted.append(
                {
                    "unit_id": str(entity.get("entity_id", entity.get("uid", "unknown"))),
                    "position": [lat, lon, hae],
                    "entity_type": str(entity.get("entity_type", "unknown")),
                    "affiliation": affiliation,
                    "domain": domain,
                    "callsign": str(entity.get("marking", "")),
                }
            )

        count = self.publish_tracks(converted)
        self._stats["crossfed"] += count
        return count

    def get_stats(self) -> dict:
        return dict(self._stats)

    @staticmethod
    def _read_dis_entities(dis_adapter: Any) -> list[dict]:
        if hasattr(dis_adapter, "receive_entities"):
            try:
                rows = dis_adapter.receive_entities()
                if isinstance(rows, list):
                    return rows
            except Exception:
                return []
        if hasattr(dis_adapter, "get_received_entities"):
            try:
                values = dis_adapter.get_received_entities()
                if isinstance(values, dict):
                    return [row for row in values.values() if isinstance(row, dict)]
            except Exception:
                return []
        return []

    @staticmethod
    def _domain_from_entity(entity: dict) -> str:
        entity_type = entity.get("entity_type")
        if isinstance(entity_type, dict):
            domain_id = int(entity_type.get("domain", 1))
            return {2: "air", 3: "surface"}.get(domain_id, "ground")
        if isinstance(entity_type, str):
            text = entity_type.lower()
            if "air" in text or "uav" in text:
                return "air"
            if "surface" in text or "ship" in text:
                return "surface"
        return "ground"

